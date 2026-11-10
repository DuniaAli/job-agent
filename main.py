"""
Job application agent: the file you run.

Commands (run them in the PyCharm terminal):

  python main.py test-claude        check your Anthropic API key works
  python main.py test-sheet         check Google Sheets is connected
  python main.py fetch              find new jobs and show them (no Claude, no Sheet)
  python main.py run                the full daily run
  python main.py run --limit 5      full run, but score at most 5 jobs
  python main.py run --no-sheet     full run without Google Sheets (letters still saved)
  python main.py letter --file advert.txt --company "Acme" --title "Junior Engineer"
                                    score and write a letter for an advert you pasted into a file
  python main.py answer an application form question in your voice
  python main.py applied JOB_ID     mark a job as applied in the Sheet
  python main.py eval               compare the agent's verdicts with yours

The agent never submits an application. You always do that yourself.
"""

import argparse
import datetime
import os
import re
import sys

from dotenv import load_dotenv

import config
import fetchers
import filters
import llm
import prompts

load_dotenv()


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
def read_text_file(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def load_profile():
    fact_bank = read_text_file(config.FACT_BANK_FILE)
    voice_sample = read_text_file(config.VOICE_SAMPLE_FILE)
    if "[CONFIRM" in fact_bank:
        print("REMINDER: data/fact_bank.md still has [CONFIRM] notes. Fill them in when you can.\n")
    return fact_bank, voice_sample


def safe_filename(text):
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return cleaned[:60]


def save_letter(job, letter):
    os.makedirs(config.LETTERS_FOLDER, exist_ok=True)
    date_text = datetime.date.today().isoformat()
    name = f"{date_text}_{safe_filename(job['company'])}_{safe_filename(job['title'])}.txt"
    path = os.path.join(config.LETTERS_FOLDER, name)
    with open(path, "w", encoding="utf-8") as file:
        file.write(f"{job['company']} | {job['title']}\n{job['url']}\n\n")
        file.write(letter)
    return path


# ---------------------------------------------------------------
# The three Claude steps
# ---------------------------------------------------------------
def score_job(fact_bank, job):
    message = prompts.build_score_message(fact_bank, job)
    result = None
    reply = ""
    # Try up to two times, with plenty of room for the JSON to finish.
    for attempt in range(2):
        reply = llm.call_claude(config.SCORING_MODEL, prompts.SCORE_SYSTEM, message, max_tokens=2000)
        result = llm.parse_json_reply(reply)
        if result is not None:
            break
        print(f"  Could not read the score reply (attempt {attempt + 1} of 2)")
    if result is None:
        print("  WARNING: still unreadable. Start of the reply was:")
        print("  " + reply[:300].replace("\n", " "))
        # failed=True tells the run loop NOT to mark this job as seen.
        return {"score": 0, "verdict": "skip", "reasons": ["scoring reply was not valid JSON"],
                "red_flags": [], "hard_blockers": [], "best_hooks": [], "company_hook": "",
                "failed": True}
    # Make sure score is a number even if Claude sent "72".
    try:
        result["score"] = int(result.get("score", 0))
    except (TypeError, ValueError):
        result["score"] = 0
    return result


def check_letter(fact_bank, job, letter):
    message = prompts.build_check_message(fact_bank, job, letter)
    reply = llm.call_claude(config.WRITING_MODEL, prompts.CHECK_SYSTEM, message, max_tokens=3000)
    result = llm.parse_json_reply(reply)
    if result is None:
        return {"pass": False, "issues": [{"type": "style", "quote": "", "problem": "checker reply was not valid JSON", "fix": "read the letter yourself"}]}
    if "issues" not in result:
        result["issues"] = []
    # Belt and braces: our own checks that do not rely on Claude.
    if "—" in letter or "–" in letter:
        result["issues"].append({"type": "style", "quote": "dash", "problem": "letter contains a dash", "fix": "replace with a comma"})
    word_total = llm.count_words(letter)
    if word_total > 380:
        result["issues"].append({"type": "style", "quote": "", "problem": f"letter is {word_total} words", "fix": "cut to under 350 words"})
    result["pass"] = len(result["issues"]) == 0
    return result


def write_letter(fact_bank, voice_sample, job, score_result):
    """
    Draft, check, revise once, check again.
    Returns (letter, passed, notes).
    """
    message = prompts.build_letter_message(fact_bank, voice_sample, job, score_result)
    letter = llm.call_claude(config.WRITING_MODEL, prompts.LETTER_SYSTEM, message, max_tokens=4000)
    letter = llm.remove_dashes(letter)

    check = check_letter(fact_bank, job, letter)
    if check["pass"]:
        return letter, True, "Passed first check"

    print(f"  Checker found {len(check['issues'])} issue(s), revising...")
    message = prompts.build_revise_message(fact_bank, letter, check["issues"])
    letter = llm.call_claude(config.WRITING_MODEL, prompts.REVISE_SYSTEM, message, max_tokens=4000)
    letter = llm.remove_dashes(letter)

    second_check = check_letter(fact_bank, job, letter)
    if second_check["pass"]:
        return letter, True, "Passed after one revision"

    note_lines = []
    for issue in second_check["issues"]:
        note_lines.append(f"[{issue.get('type', '')}] {issue.get('quote', '')}: {issue.get('problem', '')}")
    return letter, False, " | ".join(note_lines)


# ---------------------------------------------------------------
# Commands
# ---------------------------------------------------------------
def command_test_claude():
    reply = llm.call_claude(config.SCORING_MODEL, "Reply with exactly: OK", "Test", max_tokens=10)
    print("Claude replied:", reply)


def command_test_sheet():
    import sheet
    spreadsheet = sheet.open_spreadsheet()
    print("Connected to spreadsheet:", spreadsheet.title)

    agent_ws = sheet.open_worksheet(spreadsheet)
    print(f"Agent tab '{agent_ws.title}' is ready. Rows so far: {len(agent_ws.get_all_values()) - 1}")

    tracker_ws = sheet.open_tracker_worksheet(spreadsheet)
    positions, width = sheet.find_tracker_columns(tracker_ws)
    print(f"Your tracker tab is '{tracker_ws.title}'. Columns found: {sorted(positions.keys())}")
    missing = []
    for key in ["company", "link", "cv_sent", "date", "comments"]:
        if key not in positions:
            missing.append(key)
    if len(missing) > 0:
        print("NOTE: these columns were not found, so they will be left blank:", missing)
    preview = sheet.build_tracker_row(tracker_ws, "Example Ltd", "https://example.com/job", "Example role")
    print("When you mark a job as applied, a row like this is added to your tracker.")
    print("Nothing has been written to it now:")
    print(preview)


def find_new_jobs():
    jobs = fetchers.fetch_all(config)
    print(f"\nFetched {len(jobs)} jobs in total")
    jobs = filters.apply_keyword_filters(jobs, config)
    print(f"{len(jobs)} passed the keyword filters")
    seen = filters.load_seen_jobs(config.SEEN_JOBS_FILE)
    jobs = filters.remove_seen(jobs, seen)
    print(f"{len(jobs)} are new (not seen before)\n")
    return jobs, seen


def command_fetch():
    jobs, seen = find_new_jobs()
    for job in jobs:
        print(f"- {job['company']} | {job['title']} | {job['location']}")
        print(f"  {job['url']}")


def command_run(limit, use_sheet):
    fact_bank, voice_sample = load_profile()

    worksheet = None
    if use_sheet:
        import sheet
        worksheet = sheet.open_worksheet()

    jobs, seen = find_new_jobs()
    max_to_score = config.MAX_JOBS_TO_SCORE_PER_RUN
    if limit is not None:
        max_to_score = limit
    if len(jobs) > max_to_score:
        print(f"Scoring only the first {max_to_score} jobs this run (the rest stay for next time)\n")
        jobs = jobs[:max_to_score]

    letters_written = 0
    summary = []

    for job in jobs:
        print(f"Scoring: {job['company']} | {job['title']}")
        try:
            score_result = score_job(fact_bank, job)
        except Exception as error:
            print(f"  ERROR while scoring, skipping: {error}")
            continue
        if score_result.get("failed"):
            # Do not record it, do not write it to the Sheet, try again next run.
            print("  Skipped, will retry next run")
            continue
        score = score_result["score"]
        print(f"  Score {score} ({score_result.get('verdict', '')})")
        for reason in score_result.get("reasons", []):
            print(f"    Why: {reason}")
        for flag in score_result.get("red_flags", []):
            print(f"    Red flag: {flag}")
        for blocker in score_result.get("hard_blockers", []):
            print(f"    Blocker: {blocker}")

        letter = ""
        notes = ""
        status = "Scored, no letter"
        wants_letter = score >= config.DRAFT_THRESHOLD
        if wants_letter and letters_written < config.MAX_LETTERS_PER_RUN:
            print("  Writing cover letter...")
            try:
                letter, passed, notes = write_letter(fact_bank, voice_sample, job, score_result)
                path = save_letter(job, letter)
                letters_written = letters_written + 1
                if passed:
                    status = "Ready to review"
                else:
                    status = "Needs attention"
                print(f"  {status}. Saved to {path}")
            except Exception as error:
                print(f"  ERROR while writing letter: {error}")
                status = "Needs attention"
                notes = f"Letter failed: {error}"
        elif wants_letter:
            notes = "Letter cap reached this run, run 'letter' command if you want one"

        if worksheet is not None:
            import sheet
            try:
                sheet.add_job_row(worksheet, job, score_result, status, letter, notes)
            except Exception as error:
                print(f"  ERROR writing to the Sheet: {error}")

        # Remember this job so it is never scored again.
        seen[job["job_id"]] = {"date": datetime.date.today().isoformat(), "score": score}
        filters.save_seen_jobs(config.SEEN_JOBS_FILE, seen)

        summary.append((score, job["company"], job["title"], status))

    print("\n===== Summary =====")
    summary.sort(reverse=True)
    for item in summary:
        print(f"{item[0]:>3}  {item[1]} | {item[2]}  [{item[3]}]")
    print(f"\nLetters written: {letters_written}")


def command_letter(file_path, company, title, url):
    fact_bank, voice_sample = load_profile()
    job = {
        "job_id": "manual-" + safe_filename(company + "-" + title),
        "company": company,
        "title": title,
        "location": "",
        "url": url,
        "description": read_text_file(file_path),
        "source": "pasted by me",
    }
    score_result = score_job(fact_bank, job)
    print(f"Score {score_result['score']} ({score_result.get('verdict', '')})")
    for reason in score_result.get("reasons", []):
        print("  +", reason)
    for flag in score_result.get("red_flags", []):
        print("  !", flag)
    for blocker in score_result.get("hard_blockers", []):
        print("  BLOCKER:", blocker)
    print("\nWriting letter...")
    letter, passed, notes = write_letter(fact_bank, voice_sample, job, score_result)
    path = save_letter(job, letter)
    print("\n" + letter + "\n")
    print(f"Checker: {'passed' if passed else 'NEEDS ATTENTION'} ({notes})")
    print(f"Saved to {path}")


def command_answer():
    fact_bank, voice_sample = load_profile()
    print("Paste the form question. Type END on its own line when finished:")
    question_lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        question_lines.append(line)
    question = "\n".join(question_lines)

    limit = input("Character or word limit (for example '1440 characters', or press Enter for 4 to 5 sentences): ").strip()
    if limit == "":
        limit = "4 or 5 sentences"
    context = input("Company and role (optional, press Enter to skip): ").strip()

    message = prompts.build_answer_message(fact_bank, voice_sample, question, context, limit)
    answer = llm.call_claude(config.WRITING_MODEL, prompts.ANSWER_SYSTEM, message, max_tokens=4000)
    answer = llm.remove_dashes(answer)
    print("\n" + answer)
    print(f"\n({len(answer)} characters, {llm.count_words(answer)} words)")


def command_applied(job_id):
    import sheet
    spreadsheet = sheet.open_spreadsheet()
    agent_ws = sheet.open_worksheet(spreadsheet)
    tracker_ws = sheet.open_tracker_worksheet(spreadsheet)
    result = sheet.mark_applied(agent_ws, tracker_ws, job_id)
    if result == "ok":
        print(f"Marked as applied on the '{agent_ws.title}' tab, and added a row to your '{tracker_ws.title}' tab: {job_id}")
    elif result == "already":
        print("That job is already marked as applied. Nothing was added to your tracker.")
    else:
        print("Could not find that Job ID on the agent tab")


def command_eval():
    """
    Fill in the 'My verdict' column (apply / maybe / skip) for jobs you
    have judged yourself. This shows how often the agent agrees with you.
    """
    import sheet
    worksheet = sheet.open_worksheet()
    rows = sheet.read_all_rows(worksheet)
    total = 0
    agree = 0
    disagreements = []
    for row in rows:
        mine = str(row.get("My verdict", "")).strip().lower()
        agent = str(row.get("Agent verdict", "")).strip().lower()
        if mine == "" or agent == "":
            continue
        total = total + 1
        if mine == agent:
            agree = agree + 1
        else:
            disagreements.append((row.get("Company"), row.get("Role"), agent, mine, row.get("Fit score")))
    if total == 0:
        print("No rows have 'My verdict' filled in yet.")
        return
    print(f"Agent agreed with you on {agree} of {total} jobs ({round(100 * agree / total)}%)\n")
    for item in disagreements:
        print(f"- {item[0]} | {item[1]}: agent said {item[2]} (score {item[4]}), you said {item[3]}")


# ---------------------------------------------------------------
# Command line entry point
# ---------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Job application agent")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("test-claude")
    subparsers.add_parser("test-sheet")
    subparsers.add_parser("fetch")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--no-sheet", action="store_true")

    letter_parser = subparsers.add_parser("letter")
    letter_parser.add_argument("--file", required=True)
    letter_parser.add_argument("--company", required=True)
    letter_parser.add_argument("--title", required=True)
    letter_parser.add_argument("--url", default="")

    subparsers.add_parser("answer")

    applied_parser = subparsers.add_parser("applied")
    applied_parser.add_argument("job_id")

    subparsers.add_parser("eval")

    args = parser.parse_args()

    if args.command == "test-claude":
        command_test_claude()
    elif args.command == "test-sheet":
        command_test_sheet()
    elif args.command == "fetch":
        command_fetch()
    elif args.command == "run":
        command_run(args.limit, not args.no_sheet)
    elif args.command == "letter":
        command_letter(args.file, args.company, args.title, args.url)
    elif args.command == "answer":
        command_answer()
    elif args.command == "applied":
        command_applied(args.job_id)
    elif args.command == "eval":
        command_eval()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
