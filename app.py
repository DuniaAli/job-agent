"""
The web page for the job agent.

Start it from the project folder with:

    streamlit run app.py

It shows every job the agent has scored, lets you read the reasons, edit the
cover letter, and mark a job as applied. It never submits anything for you.
"""

import os

import streamlit as st
from dotenv import load_dotenv

import config
import llm
import pipeline
import store

load_dotenv()

st.set_page_config(page_title="Job Agent", layout="wide")

STYLE = """
<style>
  .block-container { padding-top: 2.2rem; max-width: 1250px; }
  .job-title { font-size: 1.5rem; font-weight: 650; margin: 0 0 0.15rem 0; line-height: 1.25; }
  .job-meta { opacity: 0.7; margin-bottom: 0.6rem; }
  .score-big { font-size: 2.6rem; font-weight: 700; line-height: 1; }
  .score-label { opacity: 0.65; font-size: 0.85rem; }
  .small-note { opacity: 0.65; font-size: 0.85rem; }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


# ---------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------
def status_color(status):
    if status == store.STATUS_READY:
        return "green"
    if status == store.STATUS_NEEDS_ATTENTION:
        return "orange"
    if status == store.STATUS_APPLIED:
        return "blue"
    if status == store.STATUS_SKIPPED:
        return "gray"
    return "violet"


def verdict_color(verdict):
    if verdict == "apply":
        return "green"
    if verdict == "maybe":
        return "orange"
    return "red"


def verdict_label(value):
    if value == "":
        return "Not set"
    return value


def setup_problems():
    """Things that are missing and would stop the agent working."""
    problems = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        problems.append("ANTHROPIC_API_KEY is missing from your .env file.")
    if not os.path.exists(config.FACT_BANK_FILE):
        problems.append(
            f"{config.FACT_BANK_FILE} not found. Copy data/fact_bank.example.md to "
            "data/fact_bank.md and fill it in with your own facts."
        )
    if not os.path.exists(config.VOICE_SAMPLE_FILE):
        problems.append(
            f"{config.VOICE_SAMPLE_FILE} not found. Copy data/voice_sample.example.md to "
            "data/voice_sample.md and paste in a letter you are happy with."
        )
    return problems


def flash(text):
    """Keeps a message across the page refresh that follows a button press."""
    st.session_state["flash"] = text


def show_flash():
    text = st.session_state.pop("flash", None)
    if text:
        st.success(text)


def count_by_status(records, wanted):
    total = 0
    for record in records:
        if record.get("status") == wanted:
            total = total + 1
    return total


def average_score(records):
    if len(records) == 0:
        return 0
    total = 0
    for record in records:
        total = total + record.get("score", 0)
    return round(total / len(records))


def filter_records(records, statuses, min_score, search):
    kept = []
    search_text = search.strip().lower()
    for record in records:
        if record.get("status") not in statuses:
            continue
        if record.get("score", 0) < min_score:
            continue
        if search_text != "":
            haystack = (record.get("company", "") + " " + record.get("title", "")).lower()
            if search_text not in haystack:
                continue
        kept.append(record)
    return kept


# ---------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------
def draw_sidebar(records):
    st.sidebar.header("Job Agent")
    st.sidebar.caption("Finds roles, scores the fit, drafts letters in your voice and fact checks them. You review and apply.")

    problems = setup_problems()
    if len(problems) > 0:
        for problem in problems:
            st.sidebar.error(problem)

    st.sidebar.subheader("Find new jobs")
    limit = st.sidebar.number_input(
        "Jobs to score this run", min_value=1, max_value=config.MAX_JOBS_TO_SCORE_PER_RUN,
        value=min(10, config.MAX_JOBS_TO_SCORE_PER_RUN), step=1,
        help="Each job costs a little in API credit. Start small.",
    )
    use_sheet = st.sidebar.checkbox(
        "Also write to my Google Sheet", value=False,
        help="Needs the Google Sheet set up in .env. Leave off to keep everything local.",
    )
    run_clicked = st.sidebar.button("Find and score new jobs", type="primary", use_container_width=True)

    st.sidebar.subheader("Filter the queue")
    default_statuses = [store.STATUS_READY, store.STATUS_NEEDS_ATTENTION, store.STATUS_SCORED_ONLY]
    statuses = st.sidebar.multiselect("Show jobs that are", store.ALL_STATUSES, default=default_statuses)
    min_score = st.sidebar.slider("Minimum score", 0, 100, 0)
    search = st.sidebar.text_input("Search company or role")

    judged, agreed = store.agreement_with_agent(records)
    if judged > 0:
        st.sidebar.subheader("How well the agent knows you")
        st.sidebar.write(f"Agreed with you on {agreed} of {judged} jobs you judged.")

    return limit, use_sheet, run_clicked, statuses, min_score, search


def handle_run(limit, use_sheet):
    with st.status("Finding and scoring jobs...", expanded=True) as status_box:
        try:
            counts = pipeline.run_pipeline(int(limit), use_sheet, st.write)
        except FileNotFoundError as error:
            status_box.update(label="Setup needed", state="error")
            st.error(f"A file is missing: {error}")
            return
        except Exception as error:
            status_box.update(label="The run stopped with an error", state="error")
            st.error(str(error))
            return
        label = (
            f"Done. Scored {counts['scored']} jobs, wrote {counts['letters']} letters"
            f" ({counts['failed']} could not be scored)."
        )
        status_box.update(label=label, state="complete")
    flash(label)
    st.rerun()


# ---------------------------------------------------------------
# Review queue tab
# ---------------------------------------------------------------
def draw_summary(records):
    columns = st.columns(4)
    columns[0].metric("To review", count_by_status(records, store.STATUS_READY))
    columns[1].metric("Needs attention", count_by_status(records, store.STATUS_NEEDS_ATTENTION))
    columns[2].metric("Applied", count_by_status(records, store.STATUS_APPLIED))
    columns[3].metric("Average score", average_score(records))


def draw_table(visible):
    rows = []
    for record in visible:
        rows.append({
            "Score": record.get("score", 0),
            "Company": record.get("company", ""),
            "Role": record.get("title", ""),
            "Verdict": record.get("verdict", ""),
            "Status": record.get("status", ""),
        })
    event = st.dataframe(
        rows,
        hide_index=True,
        use_container_width=True,
        height=min(48 + 35 * len(rows), 420),
        on_select="rerun",
        selection_mode="single-row",
        key="job_table",
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%d", width="small"),
            "Company": st.column_config.TextColumn("Company", width="medium"),
            "Role": st.column_config.TextColumn("Role", width="large"),
            "Verdict": st.column_config.TextColumn("Verdict", width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
        },
    )
    selected_rows = event.selection.rows
    if len(selected_rows) == 0:
        return None
    return visible[selected_rows[0]]


def draw_reasons(record):
    left, right = st.columns(2)
    with left:
        st.markdown("**Why it could fit**")
        reason_lines = []
        for reason in record.get("reasons", []):
            reason_lines.append("- " + reason)
        if len(reason_lines) == 0:
            st.caption("Nothing recorded.")
        else:
            st.markdown("\n".join(reason_lines))
    with right:
        st.markdown("**Watch out for**")
        flag_lines = []
        for blocker in record.get("hard_blockers", []):
            flag_lines.append("- **Blocker:** " + blocker)
        for flag in record.get("red_flags", []):
            flag_lines.append("- " + flag)
        if len(flag_lines) == 0:
            st.caption("Nothing flagged.")
        else:
            st.markdown("\n".join(flag_lines))


def draw_job_detail(record, use_sheet):
    job_id = record["job_id"]
    status = record.get("status", "")

    with st.container(border=True):
        head_left, head_right = st.columns([5, 1])
        with head_left:
            st.markdown(f"<div class='job-title'>{record.get('title', '')}</div>", unsafe_allow_html=True)
            meta = record.get("company", "")
            if record.get("location"):
                meta = meta + "  |  " + record["location"]
            if record.get("source"):
                meta = meta + "  |  " + record["source"]
            st.markdown(f"<div class='job-meta'>{meta}</div>", unsafe_allow_html=True)
            badges = f":{status_color(status)}-badge[{status}]"
            if record.get("verdict"):
                badges = badges + f" :{verdict_color(record['verdict'])}-badge[Agent says {record['verdict']}]"
            st.markdown(badges)
        with head_right:
            st.markdown(f"<div class='score-big'>{record.get('score', 0)}</div><div class='score-label'>fit score</div>", unsafe_allow_html=True)
            if record.get("url"):
                st.link_button("Open the advert", record["url"], use_container_width=True)

        draw_reasons(record)

        if record.get("description"):
            with st.expander("Advert text the agent read"):
                st.text(record["description"][:8000])

    draw_letter_panel(record, use_sheet)


def draw_letter_panel(record, use_sheet):
    job_id = record["job_id"]
    status = record.get("status", "")
    letter = record.get("letter", "")

    with st.container(border=True):
        st.markdown("**Cover letter**")
        notes = record.get("notes", "")
        if letter == "":
            if notes:
                st.caption(notes)
            st.caption("No letter yet. Jobs below the draft threshold do not get one automatically.")
            if st.button("Write a letter for this job", key="write_" + job_id):
                run_letter(job_id)
        else:
            if status == store.STATUS_NEEDS_ATTENTION:
                st.warning("The fact checker still had concerns. Read every line against your real experience. " + notes)
            elif notes:
                st.caption("Checker: " + notes)

            key = "letter_" + job_id
            edited = st.text_area("Edit freely, then save", value=letter, height=430, key=key, label_visibility="collapsed")
            words = len(edited.split())
            st.caption(f"{words} words. Check every claim against the advert and your own history before you send.")

            buttons = st.columns(4)
            if buttons[0].button("Save my edits", key="save_" + job_id, use_container_width=True):
                store.update_record(job_id, {"letter": edited})
                flash("Edits saved.")
                st.rerun()
            buttons[1].download_button(
                "Download .txt", data=edited, file_name=f"letter_{job_id}.txt",
                key="download_" + job_id, use_container_width=True,
            )
            if buttons[2].button("Rewrite letter", key="rewrite_" + job_id, use_container_width=True):
                run_letter(job_id)
            buttons[3].caption("Rewriting replaces the text above.")

    draw_actions(record, use_sheet)


def run_letter(job_id):
    with st.spinner("Writing and fact checking the letter. This takes about a minute."):
        try:
            pipeline.write_letter_for_record(job_id)
        except Exception as error:
            st.error(f"Could not write the letter: {error}")
            return
    st.session_state.pop("letter_" + job_id, None)
    flash("Letter written. Read it carefully before you use it.")
    st.rerun()


def draw_actions(record, use_sheet):
    job_id = record["job_id"]
    status = record.get("status", "")

    with st.container(border=True):
        st.markdown("**Your decision**")
        left, middle, right = st.columns([1, 1, 2])

        if status == store.STATUS_APPLIED:
            left.button("Marked as applied", disabled=True, key="applied_" + job_id, use_container_width=True)
        elif left.button("I applied", type="primary", key="applied_" + job_id, use_container_width=True):
            try:
                message = pipeline.mark_applied(job_id, use_sheet)
            except Exception as error:
                st.error(f"Could not update: {error}")
            else:
                flash(message)
                st.rerun()

        if status == store.STATUS_SKIPPED:
            if middle.button("Put back in queue", key="restore_" + job_id, use_container_width=True):
                restored = store.STATUS_SCORED_ONLY
                if record.get("letter"):
                    restored = store.STATUS_READY
                store.update_record(job_id, {"status": restored})
                st.rerun()
        elif status != store.STATUS_APPLIED:
            if middle.button("Skip this job", key="skip_" + job_id, use_container_width=True):
                store.update_record(job_id, {"status": store.STATUS_SKIPPED})
                flash("Skipped. You can find it again by showing Skipped jobs in the sidebar.")
                st.rerun()

        options = ["", "apply", "maybe", "skip"]
        current = record.get("my_verdict", "")
        if current not in options:
            current = ""
        chosen = right.selectbox(
            "My own verdict (helps measure how well the agent judges)",
            options, index=options.index(current), format_func=verdict_label, key="verdict_" + job_id,
        )
        if chosen != current:
            store.update_record(job_id, {"my_verdict": chosen})
            st.rerun()

        if record.get("date_applied"):
            st.caption("Applied on " + record["date_applied"])
        if use_sheet:
            st.caption("Marking as applied will also update your Google Sheet.")
        st.caption("The agent never submits anything. You send every application yourself.")


def draw_queue_tab(records, statuses, min_score, search, use_sheet):
    if len(records) == 0:
        st.info(
            "No jobs yet. Press Find and score new jobs in the sidebar, "
            "or paste an advert you found yourself in the next tab."
        )
        return

    draw_summary(records)
    visible = filter_records(records, statuses, min_score, search)
    st.write("")
    if len(visible) == 0:
        st.info("No jobs match the filters in the sidebar.")
        return

    st.caption(f"{len(visible)} jobs. Click a row to read the details.")
    chosen = draw_table(visible)
    if chosen is None:
        st.caption("Select a row above to see the reasons, the letter and your options.")
        return
    draw_job_detail(chosen, use_sheet)


# ---------------------------------------------------------------
# Tab: paste an advert
# ---------------------------------------------------------------
def draw_paste_tab():
    st.markdown("Found a job somewhere the agent does not search? Paste the advert and get a score and a letter. It is saved to your queue.")
    with st.form("paste_form"):
        left, right = st.columns(2)
        company = left.text_input("Company")
        title = right.text_input("Role title")
        url = st.text_input("Link to the advert (optional)")
        description = st.text_area("Advert text", height=260, placeholder="Paste the full job description here")
        write_too = st.checkbox("Also write a cover letter", value=True)
        submitted = st.form_submit_button("Score it", type="primary")

    if not submitted:
        return
    if company.strip() == "" or title.strip() == "" or description.strip() == "":
        st.error("Company, role title and the advert text are all needed.")
        return
    with st.spinner("Reading the advert. If a letter is wanted this takes about a minute."):
        try:
            record = pipeline.score_pasted_advert(company.strip(), title.strip(), url.strip(), description, write_too)
        except Exception as error:
            st.error(f"Something went wrong: {error}")
            return
    st.success("Saved to your queue. Open the Review queue tab to edit it and mark it applied.")
    st.markdown(f"**Score {record['score']}**, agent says {record.get('verdict', '')}")
    draw_reasons(record)
    if record.get("letter"):
        st.markdown("**Cover letter**")
        st.text_area("Letter", value=record["letter"], height=400, key="pasted_letter", label_visibility="collapsed")
        if record.get("notes"):
            st.caption("Checker: " + record["notes"])


# ---------------------------------------------------------------
# Tab: application form question
# ---------------------------------------------------------------
def draw_question_tab():
    st.markdown("Paste a question from an application form and get an answer in your voice, using only your fact bank.")
    with st.form("question_form"):
        question = st.text_area("The question", height=140)
        left, right = st.columns(2)
        limit_text = left.text_input("Length limit", placeholder="For example 1440 characters. Blank means 4 or 5 sentences.")
        context = right.text_input("Company and role (optional)")
        submitted = st.form_submit_button("Write the answer", type="primary")

    if not submitted:
        return
    if question.strip() == "":
        st.error("Paste the question first.")
        return
    with st.spinner("Writing..."):
        try:
            answer = pipeline.answer_question(question, limit_text, context)
        except Exception as error:
            st.error(f"Something went wrong: {error}")
            return
    st.text_area("Answer", value=answer, height=260, key="answer_box")
    st.caption(f"{len(answer)} characters, {llm.count_words(answer)} words. Check it is true before you use it.")


# ---------------------------------------------------------------
# The page
# ---------------------------------------------------------------
def main_page():
    records = store.list_records()
    limit, use_sheet, run_clicked, statuses, min_score, search = draw_sidebar(records)

    st.title("Job Agent")
    show_flash()

    if run_clicked:
        handle_run(limit, use_sheet)

    queue_tab, paste_tab, question_tab = st.tabs(["Review queue", "Paste an advert", "Application question"])
    with queue_tab:
        draw_queue_tab(records, statuses, min_score, search, use_sheet)
    with paste_tab:
        draw_paste_tab()
    with question_tab:
        draw_question_tab()


main_page()
