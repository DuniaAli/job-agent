"""
A small local database of every job the agent has scored.

It is one JSON file (data/results.json), so the web page can show
everything the agent has found, let you edit letters, and remember
which jobs you applied for. The file is private and git-ignored.
"""

import datetime
import json
import os

RESULTS_FILE = "data/results.json"

STATUS_READY = "Ready to review"
STATUS_NEEDS_ATTENTION = "Needs attention"
STATUS_SCORED_ONLY = "Scored, no letter"
STATUS_APPLIED = "Applied"
STATUS_SKIPPED = "Skipped"

ALL_STATUSES = [
    STATUS_READY,
    STATUS_NEEDS_ATTENTION,
    STATUS_SCORED_ONLY,
    STATUS_APPLIED,
    STATUS_SKIPPED,
]


def load_results(path=None):
    """Returns a dict: job_id -> record. An empty dict if nothing is saved yet."""
    if path is None:
        path = RESULTS_FILE
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_results(results, path=None):
    """Writes to a temporary file first, so a crash cannot leave a half-written file."""
    if path is None:
        path = RESULTS_FILE
    folder = os.path.dirname(path)
    if folder != "":
        os.makedirs(folder, exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2)
    os.replace(temp_path, path)


def make_record(job, score_result, status, letter="", notes=""):
    """Builds one saved record from a job and the scoring reply."""
    return {
        "job_id": job["job_id"],
        "date_found": datetime.date.today().isoformat(),
        "company": job.get("company", ""),
        "title": job.get("title", ""),
        "location": job.get("location", ""),
        "source": job.get("source", ""),
        "url": job.get("url", ""),
        "description": job.get("description", ""),
        "score": int(score_result.get("score", 0)),
        "verdict": score_result.get("verdict", ""),
        "reasons": score_result.get("reasons", []),
        "red_flags": score_result.get("red_flags", []),
        "hard_blockers": score_result.get("hard_blockers", []),
        "best_hooks": score_result.get("best_hooks", []),
        "company_hook": score_result.get("company_hook", ""),
        "status": status,
        "letter": letter,
        "notes": notes,
        "date_applied": "",
        "my_verdict": "",
    }


def add_record(record, path=None):
    results = load_results(path)
    results[record["job_id"]] = record
    save_results(results, path)


def update_record(job_id, changes, path=None):
    """Changes some fields of a saved record. Returns the updated record, or None."""
    results = load_results(path)
    if job_id not in results:
        return None
    for key in changes:
        results[job_id][key] = changes[key]
    save_results(results, path)
    return results[job_id]


def list_records(path=None):
    """All records, best score first. Ties go to the newest."""
    results = load_results(path)
    records = list(results.values())
    records.sort(key=_sort_key, reverse=True)
    return records


def _sort_key(record):
    return (record.get("score", 0), record.get("date_found", ""))


def job_from_record(record):
    """Rebuilds the 'job' dict the agent functions expect."""
    return {
        "job_id": record["job_id"],
        "company": record.get("company", ""),
        "title": record.get("title", ""),
        "location": record.get("location", ""),
        "url": record.get("url", ""),
        "description": record.get("description", ""),
        "source": record.get("source", ""),
    }


def score_result_from_record(record):
    """Rebuilds the scoring reply the letter writer expects."""
    return {
        "score": record.get("score", 0),
        "verdict": record.get("verdict", ""),
        "reasons": record.get("reasons", []),
        "red_flags": record.get("red_flags", []),
        "hard_blockers": record.get("hard_blockers", []),
        "best_hooks": record.get("best_hooks", []),
        "company_hook": record.get("company_hook", ""),
    }


def agreement_with_agent(records):
    """
    Compares your own verdicts with the agent's.
    Returns (jobs you judged, jobs where you agreed).
    """
    judged = 0
    agreed = 0
    for record in records:
        mine = str(record.get("my_verdict", "")).strip().lower()
        agent = str(record.get("verdict", "")).strip().lower()
        if mine == "" or agent == "":
            continue
        judged = judged + 1
        if mine == agent:
            agreed = agreed + 1
    return judged, agreed
