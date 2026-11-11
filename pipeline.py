"""
The steps the web page runs, kept apart from the page itself.

This file reuses the functions already in main.py (score_job, write_letter
and so on), so the command line and the web page behave the same way.
The only new thing is that results are saved in store.py as well.
"""

import datetime

import config
import filters
import llm
import main
import prompts
import store


def _say(progress, text):
    if progress is not None:
        progress(text)


def letter_status(passed):
    if passed:
        return store.STATUS_READY
    return store.STATUS_NEEDS_ATTENTION


# ---------------------------------------------------------------
# The daily run
# ---------------------------------------------------------------
def run_pipeline(limit, use_sheet, progress=None):
    """
    Finds new jobs, scores them, writes letters for the good ones and saves
    everything. Returns a dict of counts. progress(text) is called with
    short messages so a web page can show what is happening.
    """
    fact_bank, voice_sample = main.load_profile()

    worksheet = None
    if use_sheet:
        import sheet
        worksheet = sheet.open_worksheet()

    _say(progress, "Fetching jobs from your sources...")
    jobs, seen = main.find_new_jobs()
    _say(progress, f"{len(jobs)} new jobs after filters")

    max_to_score = config.MAX_JOBS_TO_SCORE_PER_RUN
    if limit is not None:
        max_to_score = limit
    if len(jobs) > max_to_score:
        jobs = jobs[:max_to_score]
        _say(progress, f"Scoring the first {max_to_score} (the rest wait for next time)")

    counts = {"found": len(jobs), "scored": 0, "letters": 0, "failed": 0}

    for job in jobs:
        _say(progress, f"Scoring {job['company']}, {job['title']}")
        try:
            score_result = main.score_job(fact_bank, job)
        except Exception as error:
            _say(progress, f"Could not score {job['company']}: {error}")
            counts["failed"] = counts["failed"] + 1
            continue
        if score_result.get("failed"):
            _say(progress, "Reply unreadable, will retry next run")
            counts["failed"] = counts["failed"] + 1
            continue

        score = score_result["score"]
        letter = ""
        notes = ""
        status = store.STATUS_SCORED_ONLY
        wants_letter = score >= config.DRAFT_THRESHOLD
        if wants_letter and counts["letters"] < config.MAX_LETTERS_PER_RUN:
            _say(progress, f"Score {score}. Writing a letter...")
            try:
                letter, passed, notes = main.write_letter(fact_bank, voice_sample, job, score_result)
                main.save_letter(job, letter)
                counts["letters"] = counts["letters"] + 1
                status = letter_status(passed)
            except Exception as error:
                status = store.STATUS_NEEDS_ATTENTION
                notes = f"Letter failed: {error}"
        elif wants_letter:
            notes = "Letter cap reached this run. Use Write letter on this job if you want one."

        store.add_record(store.make_record(job, score_result, status, letter, notes))

        if worksheet is not None:
            import sheet
            try:
                sheet.add_job_row(worksheet, job, score_result, status, letter, notes)
            except Exception as error:
                _say(progress, f"Could not write to the Sheet: {error}")

        seen[job["job_id"]] = {"date": datetime.date.today().isoformat(), "score": score}
        filters.save_seen_jobs(config.SEEN_JOBS_FILE, seen)
        counts["scored"] = counts["scored"] + 1

    return counts


# ---------------------------------------------------------------
# Letters
# ---------------------------------------------------------------
def write_letter_for_record(job_id):
    """Writes (or rewrites) the letter for a saved job. Returns the updated record."""
    results = store.load_results()
    record = results[job_id]
    fact_bank, voice_sample = main.load_profile()
    job = store.job_from_record(record)
    score_result = store.score_result_from_record(record)
    letter, passed, notes = main.write_letter(fact_bank, voice_sample, job, score_result)
    main.save_letter(job, letter)
    changes = {"letter": letter, "notes": notes, "status": letter_status(passed)}
    if record.get("status") == store.STATUS_APPLIED:
        changes["status"] = store.STATUS_APPLIED
    return store.update_record(job_id, changes)


def score_pasted_advert(company, title, url, description, write_letter_too):
    """
    For an advert you paste in yourself. Scores it, optionally writes a
    letter, saves it to the queue and returns the saved record.
    """
    fact_bank, voice_sample = main.load_profile()
    job = {
        "job_id": "manual-" + main.safe_filename(company + "-" + title),
        "company": company,
        "title": title,
        "location": "",
        "url": url,
        "description": description,
        "source": "pasted by me",
    }
    score_result = main.score_job(fact_bank, job)
    if score_result.get("failed"):
        raise RuntimeError("Claude's scoring reply could not be read. Try again.")
    letter = ""
    notes = ""
    status = store.STATUS_SCORED_ONLY
    if write_letter_too:
        letter, passed, notes = main.write_letter(fact_bank, voice_sample, job, score_result)
        main.save_letter(job, letter)
        status = letter_status(passed)
    record = store.make_record(job, score_result, status, letter, notes)
    store.add_record(record)
    return record


# ---------------------------------------------------------------
# Application form questions
# ---------------------------------------------------------------
def answer_question(question, limit_text, context):
    fact_bank, voice_sample = main.load_profile()
    if limit_text.strip() == "":
        limit_text = "4 or 5 sentences"
    message = prompts.build_answer_message(fact_bank, voice_sample, question, context, limit_text)
    answer = llm.call_claude(config.WRITING_MODEL, prompts.ANSWER_SYSTEM, message, max_tokens=4000)
    return llm.remove_dashes(answer)


# ---------------------------------------------------------------
# Marking a job as applied
# ---------------------------------------------------------------
def mark_applied(job_id, use_sheet):
    """
    Marks a job as applied. With use_sheet on, also updates your Google
    Sheet (the Agent tab and your own tracker tab). The Sheet is done
    first, so a Sheet problem leaves the job unmarked here too.
    Returns a short message for the page.
    """
    results = store.load_results()
    record = results[job_id]
    if record.get("status") == store.STATUS_APPLIED:
        return "Already marked as applied."

    message = "Marked as applied."
    if use_sheet:
        import sheet
        spreadsheet = sheet.open_spreadsheet()
        agent_ws = sheet.open_worksheet(spreadsheet)
        tracker_ws = sheet.open_tracker_worksheet(spreadsheet)
        result = sheet.mark_applied(agent_ws, tracker_ws, job_id)
        if result == "not_found":
            # This job was never written to the Sheet, so add it first.
            sheet.add_job_row(
                agent_ws,
                store.job_from_record(record),
                store.score_result_from_record(record),
                record.get("status", ""),
                record.get("letter", ""),
                record.get("notes", ""),
            )
            result = sheet.mark_applied(agent_ws, tracker_ws, job_id)
        if result == "already":
            message = "Marked as applied. The Sheet already had it, so no new tracker row was added."
        else:
            message = "Marked as applied and added to your tracker."

    store.update_record(job_id, {
        "status": store.STATUS_APPLIED,
        "date_applied": datetime.date.today().isoformat(),
    })
    return message
