"""
Fetches job adverts from public job APIs and turns every advert
into the same simple dictionary shape:

    {
        "job_id": "greenhouse-monzo-12345",
        "company": "Monzo",
        "title": "Junior Software Engineer",
        "location": "London",
        "url": "https://...",
        "description": "plain text of the advert",
        "source": "greenhouse",
    }

No scraping: every source here is an official public API.
"""

import html
import os
import re

import requests

TIMEOUT_SECONDS = 20


def html_to_text(raw_html):
    """Turns an HTML job description into plain text."""
    if raw_html is None:
        return ""
    text = html.unescape(raw_html)
    # Line breaks for block elements so paragraphs stay apart.
    text = re.sub(r"<\s*(br|/p|/li|/h[1-6]|/div)\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def get_json(url, params=None):
    """Calls a URL and returns parsed JSON, or None if anything fails."""
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as error:
        print(f"  WARNING: could not reach {url}: {error}")
        return None
    if response.status_code != 200:
        print(f"  WARNING: {url} returned status {response.status_code}")
        return None
    try:
        return response.json()
    except ValueError:
        print(f"  WARNING: {url} did not return JSON")
        return None


# ---------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------
def fetch_greenhouse(company, slug):
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = get_json(url, params={"content": "true"})
    jobs = []
    if data is None:
        return jobs
    for item in data.get("jobs", []):
        location = ""
        if item.get("location"):
            location = item["location"].get("name", "")
        job = {
            "job_id": f"greenhouse-{slug}-{item.get('id')}",
            "company": company,
            "title": item.get("title", ""),
            "location": location,
            "url": item.get("absolute_url", ""),
            "description": html_to_text(item.get("content", "")),
            "source": "greenhouse",
        }
        jobs.append(job)
    return jobs


# ---------------------------------------------------------------
# Lever (some UK companies use the EU server)
# ---------------------------------------------------------------
def fetch_lever(company, slug, eu=False):
    if eu:
        url = f"https://api.eu.lever.co/v0/postings/{slug}"
    else:
        url = f"https://api.lever.co/v0/postings/{slug}"
    data = get_json(url, params={"mode": "json"})
    jobs = []
    if data is None:
        return jobs
    for item in data:
        location = ""
        if item.get("categories"):
            location = item["categories"].get("location", "") or ""
        # Lever splits the advert into a description plus lists
        # (Requirements, Responsibilities...). Join them all.
        parts = [item.get("descriptionPlain", "") or ""]
        for section in item.get("lists", []):
            parts.append(section.get("text", ""))
            parts.append(html_to_text(section.get("content", "")))
        parts.append(item.get("additionalPlain", "") or "")
        job = {
            "job_id": f"lever-{slug}-{item.get('id')}",
            "company": company,
            "title": item.get("text", ""),
            "location": location,
            "url": item.get("hostedUrl", ""),
            "description": "\n\n".join(parts).strip(),
            "source": "lever",
        }
        jobs.append(job)
    return jobs


# ---------------------------------------------------------------
# Ashby
# ---------------------------------------------------------------
def fetch_ashby(company, slug):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    data = get_json(url)
    jobs = []
    if data is None:
        return jobs
    for item in data.get("jobs", []):
        description = item.get("descriptionPlain")
        if not description:
            description = html_to_text(item.get("descriptionHtml", ""))
        job = {
            "job_id": f"ashby-{slug}-{item.get('id')}",
            "company": company,
            "title": item.get("title", ""),
            "location": item.get("location", "") or "",
            "url": item.get("jobUrl", ""),
            "description": description,
            "source": "ashby",
        }
        jobs.append(job)
    return jobs


# ---------------------------------------------------------------
# Adzuna (aggregates many UK job boards)
# Note: Adzuna only gives a short snippet of each advert, so scores
# for Adzuna jobs are rougher. Always open the link before applying.
# ---------------------------------------------------------------
KM_PER_MILE = 1.609


def miles_to_km(miles):
    return int(round(miles * KM_PER_MILE))


def fetch_adzuna(what, where, max_days_old, results_per_page, distance_miles=None):
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")
    jobs = []
    if not app_id or not app_key:
        print("  WARNING: ADZUNA_APP_ID or ADZUNA_APP_KEY missing in .env, skipping Adzuna")
        return jobs
    url = "https://api.adzuna.com/v1/api/jobs/gb/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "what": what,
        "where": where,
        "max_days_old": max_days_old,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }
    # Only jobs within this many miles of "where". Adzuna wants km, so convert.
    # Leave distance_miles out for a plain place search such as "London".
    if distance_miles is not None:
        params["distance"] = miles_to_km(distance_miles)
    data = get_json(url, params=params)
    if data is None:
        return jobs
    for item in data.get("results", []):
        company = ""
        if item.get("company"):
            company = item["company"].get("display_name", "")
        location = ""
        if item.get("location"):
            location = item["location"].get("display_name", "")
        job = {
            "job_id": f"adzuna-{item.get('id')}",
            "company": company,
            "title": html_to_text(item.get("title", "")),
            "location": location,
            "url": item.get("redirect_url", ""),
            "description": html_to_text(item.get("description", "")),
            "source": "adzuna (snippet only)",
        }
        jobs.append(job)
    return jobs


# ---------------------------------------------------------------
# Run every source in config.py
# ---------------------------------------------------------------
def fetch_all(config):
    all_jobs = []

    for board in config.COMPANY_BOARDS:
        company = board["company"]
        ats = board["ats"]
        slug = board["slug"]
        print(f"Fetching {company} ({ats})...")
        if ats == "greenhouse":
            found = fetch_greenhouse(company, slug)
        elif ats == "lever":
            found = fetch_lever(company, slug, eu=False)
        elif ats == "lever_eu":
            found = fetch_lever(company, slug, eu=True)
        elif ats == "ashby":
            found = fetch_ashby(company, slug)
        else:
            print(f"  WARNING: unknown ats '{ats}' for {company}")
            found = []
        print(f"  {len(found)} jobs")
        for job in found:
            all_jobs.append(job)

    for search in config.ADZUNA_SEARCHES:
        distance_miles = search.get("distance_miles")
        if distance_miles is None:
            print(f"Searching Adzuna: {search['what']} in {search['where']}...")
        else:
            print(f"Searching Adzuna: {search['what']} within {distance_miles} miles of {search['where']}...")
        found = fetch_adzuna(
            search["what"],
            search["where"],
            config.ADZUNA_MAX_DAYS_OLD,
            config.ADZUNA_RESULTS_PER_SEARCH,
            distance_miles,
        )
        print(f"  {len(found)} jobs")
        for job in found:
            all_jobs.append(job)

    # The same job often appears in several Adzuna searches.
    unique_jobs = []
    ids_already_added = set()
    for job in all_jobs:
        if job["job_id"] in ids_already_added:
            continue
        ids_already_added.add(job["job_id"])
        unique_jobs.append(job)

    return unique_jobs