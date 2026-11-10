"""
All the settings you are likely to change live in this file.
Edit these, not the other files, when you want different searches.
"""

# ---------------------------------------------------------------
# Claude models
# A cheap fast model scores jobs, a stronger model writes letters.
# ---------------------------------------------------------------
SCORING_MODEL = "claude-haiku-5-5"
WRITING_MODEL = "claude-sonnet-5-5"

# ---------------------------------------------------------------
# Adzuna searches (broad coverage of UK job boards)
# Each search is run separately. Keep the list short to save calls.
# ---------------------------------------------------------------
ADZUNA_SEARCHES = [
    {"what": "graduate software engineer", "where": "London"},
    {"what": "junior software engineer", "where": "London"},
    {"what": "junior python developer", "where": "London"},
    {"what": "graduate AI engineer", "where": "London"},
    {"what": "forward deployed engineer", "where": "London"},
    {"what": "EHR analyst", "where": "London"},
    {"what": "clinical systems analyst", "where": "London"},
]
ADZUNA_MAX_DAYS_OLD = 3
ADZUNA_RESULTS_PER_SEARCH = 50

# ---------------------------------------------------------------
# Company career boards you want watched directly.
# How to find a slug: open the company's careers page and look at
# the address of a job advert.
#   boards.greenhouse.io/SLUG/...  or  job-boards.greenhouse.io/SLUG
#   jobs.lever.co/SLUG/...         (jobs.eu.lever.co/SLUG means "lever_eu")
#   jobs.ashbyhq.com/SLUG/...
# A wrong slug is fine: the agent prints a warning and moves on.
# ---------------------------------------------------------------
COMPANY_BOARDS = [
    # {"company": "Example Ltd", "ats": "greenhouse", "slug": "example"},
    # {"company": "Example Two", "ats": "lever", "slug": "exampletwo"},
    # {"company": "Example EU", "ats": "lever_eu", "slug": "exampleeu"},
    # {"company": "Example Three", "ats": "ashby", "slug": "examplethree"},
    {"company": "accuRx", "ats": "ashby", "slug": "accurx"},
]

# ---------------------------------------------------------------
# Cheap keyword filter, run BEFORE Claude sees anything.
# A job title must contain at least one INCLUDE word
# and none of the EXCLUDE words.
# ---------------------------------------------------------------
TITLE_INCLUDE = [
    "software", "engineer", "developer", "python", "ai ", " ai", "machine learning",
    "ml ", "data", "forward deployed", "solutions", "analyst", "ehr", "epic",
    "clinical systems", "prompt", "evaluation", "graduate", "junior", "associate",
]
TITLE_EXCLUDE = [
    "senior", "sr.", "sr ", "lead", "principal", "staff", "head of", "director",
    "manager", "architect", "vp ", "chief", "intern ", "internship",
    "c++", "c#", ".net", "embedded", "firmware", "ios", "android",
]
LOCATION_INCLUDE = [
    "london", "remote", "united kingdom", "uk", "england", "bracknell",
    "reading", "berkshire", "hybrid",
]

# ---------------------------------------------------------------
# Scoring and drafting
# ---------------------------------------------------------------
# Jobs scoring at or above this get a cover letter drafted.
DRAFT_THRESHOLD = 65
# Safety cap: the most jobs Claude will score in one run.
MAX_JOBS_TO_SCORE_PER_RUN = 40
# Safety cap: the most cover letters drafted in one run.
MAX_LETTERS_PER_RUN = 5

# ---------------------------------------------------------------
# Files
# ---------------------------------------------------------------
FACT_BANK_FILE = "data/fact_bank.md"
VOICE_SAMPLE_FILE = "data/voice_sample.md"
SEEN_JOBS_FILE = "data/seen_jobs.json"
LETTERS_FOLDER = "output/letters"
