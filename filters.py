"""
Cheap filters that run before Claude, plus a small memory of jobs
already looked at, so the same advert is never scored twice.
"""

import json
import os


def title_passes(title, include_words, exclude_words):
    # Spaces at both ends so words like "ai " still match at the end.
    padded = " " + title.lower() + " "
    for word in exclude_words:
        if word in padded:
            return False
    for word in include_words:
        if word in padded:
            return True
    return False


def location_passes(location, include_words):
    # Many adverts leave location blank. Keep those, Claude will judge.
    if location is None or location.strip() == "":
        return True
    lowered = location.lower()
    for word in include_words:
        if word in lowered:
            return True
    return False


def apply_keyword_filters(jobs, config):
    kept = []
    for job in jobs:
        if not title_passes(job["title"], config.TITLE_INCLUDE, config.TITLE_EXCLUDE):
            continue
        if not location_passes(job["location"], config.LOCATION_INCLUDE):
            continue
        kept.append(job)
    return kept


# ---------------------------------------------------------------
# Seen jobs memory (a JSON file in the data folder)
# ---------------------------------------------------------------
def load_seen_jobs(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_seen_jobs(path, seen):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(seen, file, indent=2)


def remove_seen(jobs, seen):
    new_jobs = []
    for job in jobs:
        if job["job_id"] not in seen:
            new_jobs.append(job)
    return new_jobs
