# Job Application Agent: step by step build guide

This agent does the boring half of job hunting for you:

1. **Finds** new job adverts through official public job APIs (Adzuna, plus any Greenhouse, Lever or Ashby company boards you add).
2. **Filters** them with cheap keyword rules (no senior roles, no C++ roles, London, remote or nearby only).
3. **Scores** each one with Claude against your real profile, and flags hard blockers like "3+ years required".
4. **Writes** a tailored cover letter for the best matches, in your voice.
5. **Fact checks** every letter in a second, separate Claude pass, and revises it once if anything is wrong.
6. **Logs** everything to your Google Sheet with the status "Ready to review".

**You** read the letter, tweak it, and submit the application yourself. Then you run one command and the Sheet says "Applied".

```
 Adzuna / Greenhouse / Lever / Ashby
              |
        keyword filter  (free)
              |
       skip jobs seen before
              |
     Claude Haiku: score 0 to 100  ---> below 65: logged, no letter
              |
     Claude Sonnet: draft letter
              |
     Claude Sonnet: fact check  ---> problems? revise once, check again
              |
   letter saved + row in Google Sheet  ---> YOU review and submit
```

---

## Project files

```
job_agent/
  main.py            the file you run (all commands)
  config.py          your searches, filters and thresholds: edit this
  prompts.py         every prompt sent to Claude
  fetchers.py        talks to the job APIs
  filters.py         keyword filters and "seen before" memory
  llm.py             talks to Claude, plus the dash remover
  sheet.py           talks to Google Sheets
  data/
    fact_bank.md     EVERYTHING the agent may say about you (most important file)
    voice_sample.md  a letter that sounds like you
  output/letters/    every letter the agent writes is saved here
  requirements.txt   libraries to install
  .env.example       template for your secret keys
```

---

## Step 1. Set up the project in PyCharm (10 minutes)

1. Unzip `job_agent.zip` somewhere sensible, for example `Documents/Projects/job_agent`.
2. Open PyCharm, choose **File > Open**, and pick the `job_agent` folder.
3. Set up the Python environment. Pick one:

   **Option A: uv (recommended)**
   - Install uv once. Mac: open Terminal and run `curl -LsSf https://astral.sh/uv/install.sh | sh`. Windows: open PowerShell and run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - In PyCharm open the **Terminal** tab at the bottom and run:
     ```
     uv venv
     uv pip install -r requirements.txt
     ```
   - Go to **Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter > Select existing**, set **Type** to **Python** and browse to `.venv/bin/python` inside the project. (If PyCharm's "uv" type shows `[invalid]`, this plain Python route avoids it.)
   - In the terminal, activate the environment with `source .venv/bin/activate`. The prompt then starts with `(job_agent)`. Or put `uv run` in front of any command instead.

   **Option B: plain pip**
   - **Settings > Project > Python Interpreter > Add Interpreter > Add Local Interpreter > Virtualenv**, new environment in `.venv`, Python 3.11 or newer.
   - In the PyCharm Terminal: `pip install -r requirements.txt`

4. Check it worked: in the Terminal run `python main.py`. You should see the list of commands.

> Close and reopen the Terminal tab after setting the interpreter, so it uses `.venv`. You will see `(.venv)` at the start of the line.

---

## Step 2. Get your Anthropic API key (5 minutes)

1. Go to **console.anthropic.com** and sign in (you already used the API at Mattis, so you may have an account).
2. **Settings > Billing**: add a small amount of credit. **Set a monthly spend limit** (for example £10) so a mistake can never cost much.
3. **API Keys > Create Key**. Copy it straight away; it is shown once.
4. In PyCharm, right click `.env.example`, **Copy**, then paste it into the same folder and name it `.env`.
5. Open `.env` and paste your key after `ANTHROPIC_API_KEY=`.
6. Test it:
   ```
   python main.py test-claude
   ```
   You should see `Claude replied: OK`.

**Cost guide:** scoring uses Haiku, the cheap model, and only about 5 letters are written per run with Sonnet. A normal daily run should cost pennies, not pounds. Check the **Usage** page in the Console after your first few runs to see your real numbers.

---

## Step 3. Get your Adzuna key (5 minutes)

Adzuna collects jobs from lots of UK job boards and gives you an official free API for them.

1. Go to **developer.adzuna.com** and sign up.
2. Open your dashboard; you will see an **Application ID** and an **Application Key**.
3. Paste them into `.env` after `ADZUNA_APP_ID=` and `ADZUNA_APP_KEY=`.
4. Test it:
   ```
   python main.py fetch
   ```
   This finds and filters jobs and prints them. It uses no Claude credit and does not touch your Sheet.

Adzuna only gives a short snippet of each advert, so scores for Adzuna jobs are rougher. The Sheet marks these as `adzuna (snippet only)`. Always open the link before you apply.

---

## Step 4. Connect your Google Sheet (15 minutes, the fiddliest part)

The agent logs in to Google as a **service account**, a robot Google user that only sees the sheets you share with it.

1. Go to **console.cloud.google.com**. Create a new project, for example "job-agent".
2. Search the top bar for **Google Sheets API**, open it, click **Enable**.
3. Search for **Google Drive API**, click **Enable** as well.
4. Go to **IAM & Admin > Service Accounts > Create service account**. Name it `job-agent`. Skip the optional permission steps and click **Done**.
5. Click the new service account, open the **Keys** tab, choose **Add key > Create new key > JSON**. A file downloads.
6. Rename that file to `credentials.json` and move it into your `job_agent` folder (next to `main.py`).
7. On the service account page, copy its email address. It looks like `job-agent@job-agent-12345.iam.gserviceaccount.com`.
8. **Back up first.** Open your existing "Job applications" sheet and choose **File > Make a copy**.
9. In your existing sheet, click **Share**, paste the service account email, give it **Editor** access, untick "Notify people", click **Share**.
10. Copy the Sheet ID from its address bar. In `https://docs.google.com/spreadsheets/d/1AbCdEfG.../edit` the ID is the long part between `/d/` and `/edit`.
11. Paste it into `.env` after `GOOGLE_SHEET_ID=`.
12. If your applications tab is not the first tab, put its exact name after `TRACKER_TAB_NAME=` in `.env`. Leave it blank if it is the first tab.
13. Test it:
    ```
    python main.py test-sheet
    ```
    This creates a new tab called **Agent** with the agent's own column headers. It then prints which of your columns it found and shows the row it would add to your tracker. It writes nothing to your own tab.

**How the two tabs work**
- **Agent tab:** every job the agent finds is logged here with its score, reasons, red flags and cover letter. The agent owns this tab.
- **Your tab:** the agent never changes your headers or old rows. When you run `python main.py applied JOB_ID`, it marks the job Applied on the Agent tab and adds **one row** to your tab in your own columns: company (with the link attached), CV sent = Yes, today's date, and the role title in Comments. Running `applied` twice for the same job does not add a second row.
- **Safety rule:** if the agent tab name is already used by something with content in row 1, the agent stops instead of overwriting it.

**Check these in your own sheet:**
- The date is written as `dd/mm/yyyy`. In Google Sheets go to **File > Settings** and make sure **Locale** is **United Kingdom**, so dates are read correctly.
- "CV sent" must keep **Yes** as one of its dropdown options. The agent writes the word Yes.
- Your tracker is formatted as a Google Sheets table. Adding a row at the bottom should extend it. Try it on the copy first. After your first `applied` command, look at the new row and check it sits inside the table with the dropdowns and colours.
- If you rename a column, add the new name to `TRACKER_COLUMNS` in `sheet.py`.

**Tip:** on the Agent tab, select the "Cover letter" column and use **Format > Wrapping > Clip** so long letters do not make every row huge. Click a cell to read the full letter.

---

## Step 5. Fill in your fact bank (30 minutes, the most important step)

Open `data/fact_bank.md`. This is the **only** thing the agent knows about you. If a fact is not in here, the agent is not allowed to say it, and the checker will catch it if it tries.

1. Search the file for `[CONFIRM` and fill in or fix each one (right to work, nursing degree university and year, what your LMS toolkit does, and so on). Delete the `[CONFIRM ...]` note once a line is right.
2. Read every line and ask: "Would I be happy defending this in an interview?" If not, soften or delete it.
3. Read the **DO NOT CLAIM** section. Add anything else you never want said.
4. Add new facts as they happen: a new project, a certificate, a finished Relay MVP.

Then open `data/voice_sample.md`. It holds a starter letter in your tone. **Replace it with the real cover letter you liked best**, the one that sounds most like you. The agent copies its tone, not its content.

---

## Step 6. Choose what to search for (10 minutes)

Open `config.py`.

- **ADZUNA_SEARCHES**: the job searches to run. Add or remove lines. Fewer searches means a faster run.
- **COMPANY_BOARDS**: companies you specifically want to watch. To add one, open a job advert on the company's careers page and look at the web address:
  - `boards.greenhouse.io/examplehealth/jobs/123` gives `{"company": "Example Health", "ats": "greenhouse", "slug": "examplehealth"}`
  - `jobs.lever.co/somecompany/abc` gives `"ats": "lever", "slug": "somecompany"`
  - `jobs.eu.lever.co/somecompany/abc` gives `"ats": "lever_eu"`
  - `jobs.ashbyhq.com/somecompany/abc` gives `"ats": "ashby"`

  Good ones to look up: the health tech and AI companies you liked (Healios, Skin Analytics, Heidi, Tandem, Accurx and so on). Not every company uses one of these three systems; if the advert address looks different, that company cannot be added this way, and Adzuna may still pick up its jobs.
- **TITLE_INCLUDE / TITLE_EXCLUDE / LOCATION_INCLUDE**: the free keyword filter. If good jobs are being thrown away, check here first.
- **DRAFT_THRESHOLD**: the score needed for a letter (65 to start).
- **MAX_LETTERS_PER_RUN**: how many letters per run (5 to start). Keep this small. Five good applications beat twenty rushed ones.

Run `python main.py fetch` again after any change to see what gets through.

---

## Step 7. Your first real run

Start small so you can check the quality:

```
python main.py run --limit 5
```

Watch the output. For each job you will see the score, and for good ones, "Writing cover letter..." then "Ready to review" or "Needs attention".

Then:
1. Open your Sheet. Read the "Why" and "Red flags" columns. Do the scores make sense to you?
2. Open a letter from `output/letters/`. Read it out loud. Does it sound like you? Is every fact true?
3. If something is off, fix the cause, not just the letter:
   - A wrong fact means the fact bank needs a fix or a new DO NOT CLAIM line.
   - Wrong tone means the voice sample needs replacing, or a new rule in `WRITING_RULES` in `prompts.py`.
   - Bad scores mean you should adjust the "How to score" section of `SCORE_SYSTEM` in `prompts.py`.

When you are happy, run the full version:

```
python main.py run
```

---

## Step 8. Your daily routine (about 15 minutes plus applying)

1. `python main.py run`
2. Open the Sheet, filter the Status column to **Ready to review** and **Needs attention**.
3. For each one:
   - Open the link and read the full advert.
   - Read the letter. Edit anything that is not quite you.
   - For **Needs attention**, read the "Checker notes" column first; it says exactly what to fix.
   - Apply on the company's site yourself.
   - Then run: `python main.py applied JOB_ID` (copy the Job ID from column A of the Agent tab). It marks the job Applied there and adds a row to your own applications tab.
4. Optional, but powerful: in the **My verdict** column write `apply`, `maybe` or `skip` for a few jobs a week. See Step 10.

---

## Step 9. The extra tools

**A job you found yourself on LinkedIn or anywhere else:**
1. Copy the whole advert text into a file, for example `advert.txt`, in the project folder.
2. Run:
   ```
   python main.py letter --file advert.txt --company "Healios" --title "Associate Software Engineer" --url "https://..."
   ```
   You get the score, the red flags and a checked letter, printed and saved.

**An application form question:**
```
python main.py answer
```
Paste the question, type `END` on its own line, then give the limit (for example `1440 characters`) and the company. It prints the answer with a character and word count.

---

## Step 10. Measure the agent (a good interview story)

This is the same idea as your Mattis evaluation work: a ground truth, then a measurement.

1. For 20 or more jobs in the Sheet, fill in **My verdict** with your own honest call: `apply`, `maybe` or `skip`.
2. Run:
   ```
   python main.py eval
   ```
3. It tells you how often the agent agreed with you, and lists every disagreement.
4. Look for patterns ("it keeps rating data engineering roles too high") and add a line to the scoring rules in `prompts.py`. Run eval again later and see whether agreement went up.

You can describe this in interviews: "I built an agent, created my own labelled ground truth, measured agreement, and tuned the prompts against it."

---

## Step 11 (optional). Put it on GitHub

It is a good portfolio project. The `.gitignore` already keeps your secrets out.

1. **Before your first commit**, check that `.env` and `credentials.json` are greyed out in PyCharm's project view (meaning ignored). **Never commit these.**
2. **VCS > Enable Version Control Integration > Git**, then **Git > Commit**, then **Git > GitHub > Share Project on GitHub**.
3. Think about whether you want your full `fact_bank.md` public. You might commit a cut down version instead.

---

## Step 12 (optional). Run it automatically every morning

- **Mac:** run `crontab -e` and add a line like
  `0 8 * * 1-5 cd /full/path/to/job_agent && .venv/bin/python main.py run >> run_log.txt 2>&1`
- **Windows:** open **Task Scheduler > Create Basic Task**, daily at 8:00, action "Start a program", program `C:\full\path\to\job_agent\.venv\Scripts\python.exe`, arguments `main.py run`, "Start in" `C:\full\path\to\job_agent`.

Your computer has to be on at that time. Running it by hand each morning is fine too.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| `ModuleNotFoundError` | PyCharm is not using `.venv`. Redo Step 1.3, then reopen the Terminal tab. |
| `AuthenticationError` from Anthropic | The key in `.env` is wrong or has a space in it. |
| `credit balance is too low` | Add credit in the Anthropic Console. |
| `GOOGLE_SHEET_ID is missing` | `.env` is missing the ID, or the file is called `.env.txt` by mistake. |
| `SpreadsheetNotFound` or `403` from Google | You did not share the Sheet with the service account email, or the Drive API is not enabled. |
| `FileNotFoundError: credentials.json` | The JSON key is not in the project folder, or not named exactly `credentials.json`. |
| `WARNING: ... returned status 404` | That company slug is wrong or they moved job system. Fix or remove it in `config.py`. |
| Adzuna returns 0 jobs | Check both Adzuna values in `.env`; try a broader search word. |
| Every job is filtered out | Your TITLE or LOCATION words in `config.py` are too strict. |
| A job keeps not appearing | It is in `data/seen_jobs.json`. Delete its line, or the whole file, to rescore everything. |
| Letters sound too formal or too "AI" | Replace `voice_sample.md` with your best real letter and add specific rules to `WRITING_RULES`. |

---

## How the prompts work (so you can tune them)

All prompts live in `prompts.py`:

- **WRITING_RULES**: shared rules taken from your own feedback: no dashes, no grades, never point out gaps, past tense for Mattis, only true facts, banned phrases. Add a rule whenever a letter annoys you.
- **SCORE_SYSTEM**: an honest adviser scores 0 to 100 and returns JSON with reasons, red flags, hard blockers and the best matching facts.
- **LETTER_SYSTEM**: writes in your voice, with a fixed paragraph structure and 250 to 350 words, angled by job type (health tech leans on the NHS, AI roles lead with Mattis and the dissertation, customer facing roles use Apollo).
- **CHECK_SYSTEM**: a separate strict checker compares every claim with your fact bank and the advert. It runs as a separate call because a writer marking its own work misses things.
- **REVISE_SYSTEM**: fixes only the listed problems.
- **ANSWER_SYSTEM**: form questions, 4 or 5 sentences by default, respects character limits.

As a final safety net, the code itself removes any em or en dash, and flags any letter over 380 words.
