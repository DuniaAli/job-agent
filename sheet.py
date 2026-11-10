"""
Reads and writes Google Sheets.

Two tabs are involved:

  1. The AGENT tab (named "Agent" by default). The agent owns this tab.
     Every job it finds is logged here with the score, reasons and letter.
     If the tab does not exist, it is created.

  2. Your TRACKER tab (your existing applications sheet). The agent only
     ever ADDS one row here, when you run the 'applied' command, using
     your own column names. It never changes your headers or old rows.
"""

import datetime
import os

import gspread

HEADERS = [
    "Job ID",
    "Date found",
    "Company",
    "Role",
    "Location",
    "Source",
    "Link",
    "Fit score",
    "Agent verdict",
    "Why",
    "Red flags",
    "Status",
    "Date applied",
    "Cover letter",
    "Checker notes",
    "My verdict",
]

STATUS_READY = "Ready to review"
STATUS_NEEDS_ATTENTION = "Needs attention"
STATUS_SCORED_ONLY = "Scored, no letter"
STATUS_APPLIED = "Applied"

AGENT_TAB_DEFAULT = "Agent"

# Names of the columns in YOUR tracker tab (not case sensitive).
# If you rename a column, add the new name to the list.
TRACKER_COLUMNS = {
    "company": ["company"],
    "link": ["link"],
    "cv_sent": ["cv sent"],
    "date": ["date"],
    "replied": ["company replied"],
    "comments": ["comments", "comment"],
}


# ---------------------------------------------------------------
# Opening the spreadsheet and tabs
# ---------------------------------------------------------------
def open_spreadsheet():
    credentials_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is missing from your .env file")
    client = gspread.service_account(filename=credentials_file)
    return client.open_by_key(sheet_id)


def open_worksheet(spreadsheet=None):
    """Opens the agent's own tab, creating it if needed."""
    if spreadsheet is None:
        spreadsheet = open_spreadsheet()
    tab_name = os.getenv("AGENT_TAB_NAME", AGENT_TAB_DEFAULT).strip()
    if tab_name == "":
        tab_name = AGENT_TAB_DEFAULT
    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(HEADERS))
    ensure_headers(worksheet)
    return worksheet


def open_tracker_worksheet(spreadsheet):
    """Opens YOUR existing applications tab (the first tab unless named in .env)."""
    name = os.getenv("TRACKER_TAB_NAME", "").strip()
    if name == "":
        tracker = spreadsheet.sheet1
    else:
        tracker = spreadsheet.worksheet(name)
    agent_name = os.getenv("AGENT_TAB_NAME", AGENT_TAB_DEFAULT).strip() or AGENT_TAB_DEFAULT
    if tracker.title == agent_name:
        raise RuntimeError(
            "Your tracker tab and the agent tab are the same tab. "
            "Set TRACKER_TAB_NAME in .env to the name of your own applications tab."
        )
    return tracker


def ensure_headers(worksheet):
    first_row = worksheet.row_values(1)
    if first_row == HEADERS:
        return
    has_content = False
    for value in first_row:
        if str(value).strip() != "":
            has_content = True
    if has_content:
        # Safety rule: never overwrite a tab that already has something in row 1.
        raise RuntimeError(
            f"The tab '{worksheet.title}' already has other content in row 1, "
            "so the agent will not overwrite it. Set AGENT_TAB_NAME in .env to a new tab name."
        )
    worksheet.update(values=[HEADERS], range_name="A1")


def column_number(header_name):
    # Google Sheets columns start at 1, Python lists start at 0.
    return HEADERS.index(header_name) + 1


def today():
    return datetime.date.today().isoformat()


def today_uk():
    return datetime.date.today().strftime("%d/%m/%Y")


# ---------------------------------------------------------------
# Agent tab
# ---------------------------------------------------------------
def add_job_row(worksheet, job, score_result, status, letter="", checker_notes=""):
    reasons = ""
    red_flags = ""
    score = ""
    verdict = ""
    if score_result is not None:
        score = score_result.get("score", "")
        verdict = score_result.get("verdict", "")
        reasons = "; ".join(score_result.get("reasons", []))
        flag_list = []
        for item in score_result.get("hard_blockers", []):
            flag_list.append("BLOCKER: " + item)
        for item in score_result.get("red_flags", []):
            flag_list.append(item)
        red_flags = "; ".join(flag_list)

    row = [
        job["job_id"],
        today(),
        job["company"],
        job["title"],
        job["location"],
        job["source"],
        job["url"],
        score,
        verdict,
        reasons,
        red_flags,
        status,
        "",
        letter,
        checker_notes,
        "",
    ]
    worksheet.append_row(row, value_input_option="USER_ENTERED")


def read_all_rows(worksheet):
    """Returns every row as a dict keyed by header name."""
    return worksheet.get_all_records(expected_headers=HEADERS)


# ---------------------------------------------------------------
# Your tracker tab
# ---------------------------------------------------------------
def find_tracker_columns(tracker_ws):
    """
    Reads row 1 of your tracker and works out which column is which.
    Returns (positions, width). positions maps "company", "link" and so on
    to a column index starting at 0.
    """
    headers = tracker_ws.row_values(1)
    positions = {}
    index = 0
    for header in headers:
        lowered = str(header).strip().lower()
        for key in TRACKER_COLUMNS:
            if lowered in TRACKER_COLUMNS[key]:
                positions[key] = index
        index = index + 1
    return positions, len(headers)


def build_tracker_row(tracker_ws, company, url, comment):
    """Builds one row in the shape of YOUR tracker. Writes nothing."""
    positions, width = find_tracker_columns(tracker_ws)
    if "company" not in positions:
        raise RuntimeError(
            f"Could not find a 'company' column in row 1 of the tab '{tracker_ws.title}'. "
            "Check TRACKER_TAB_NAME in .env."
        )
    row = [""] * width
    row[positions["company"]] = company
    if "link" in positions and url:
        safe_url = url.replace('"', '""')
        safe_company = company.replace('"', '""')
        row[positions["link"]] = '=HYPERLINK("' + safe_url + '","' + safe_company + '")'
    if "cv_sent" in positions:
        row[positions["cv_sent"]] = "Yes"
    if "date" in positions:
        row[positions["date"]] = today_uk()
    if "comments" in positions:
        row[positions["comments"]] = comment
    return row


def mark_applied(agent_ws, tracker_ws, job_id):
    """
    Marks the job as Applied on the agent tab, then adds one row to your
    tracker tab. Returns "ok", "already" or "not_found".
    """
    cell = agent_ws.find(job_id, in_column=column_number("Job ID"))
    if cell is None:
        return "not_found"

    values = agent_ws.row_values(cell.row)
    while len(values) < len(HEADERS):
        values.append("")

    current_status = values[HEADERS.index("Status")]
    if current_status == STATUS_APPLIED:
        # Stops the same job being added to your tracker twice.
        return "already"

    company = values[HEADERS.index("Company")]
    role = values[HEADERS.index("Role")]
    link = values[HEADERS.index("Link")]

    # Build the tracker row first, so a problem there leaves the agent tab unchanged.
    tracker_row = None
    if tracker_ws is not None:
        tracker_row = build_tracker_row(tracker_ws, company, link, role)

    agent_ws.update_cell(cell.row, column_number("Status"), STATUS_APPLIED)
    agent_ws.update_cell(cell.row, column_number("Date applied"), today())

    if tracker_row is not None:
        tracker_ws.append_row(tracker_row, value_input_option="USER_ENTERED")
    return "ok"
