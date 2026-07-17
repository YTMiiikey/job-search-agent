# Job Search Agent

An AI-powered job search pipeline for scientific and technical roles. Browse jobs as
you normally would — the Chrome extension captures them automatically. The pipeline
then scores each posting against your background and drafts tailored resumes and cover
letters, all running locally on your machine.

Designed for researchers and scientists in biotech, pharma, computational biology, and
adjacent fields. Configurable for any technical or scientific job search.

---

## How it works

```
browse / scrape → score → draft → submit → follow-up
```

| Step | What happens |
|------|-------------|
| **Capture** | Install the Chrome extension once. As you browse job postings on LinkedIn, company sites, or anywhere else, click the extension to save them. **On LinkedIn: open the full post in its own tab and wait for the description to load before clicking Save.** The pipeline also auto-scrapes company ATS boards (Greenhouse/Lever/Ashby) in bulk. |
| **Score** | Each posting is sent to Claude AI with your background summary; it assigns a 1–9 fit score and a brief rationale, saved to a local database |
| **Draft** | For jobs worth applying to, Claude generates a tailored resume summary and cover letter; pandoc converts them to DOCX and PDF |
| **Submit** | Records your submissions with platform, notes, and a follow-up date |
| **Follow-up** | Shows you which applications need a follow-up today |

All generated files stay on your machine. The only external calls are to the Anthropic API for scoring and drafting.

---

## Quickest way to get started (Claude Code)

If you use [Claude Code](https://claude.ai/code) (Anthropic's CLI), clone the repo,
open it in your terminal, and try one of these prompts:

**First-time setup**
```
Help me set up this project. I'm a computational biologist with experience in
protein structure prediction, NGS analysis, and Python/R scripting.
```
Claude will run the setup checker, ask about your background, and generate your
`user_profile.yaml` and `scripts/draft_all.py` interactively.

**Adapting to your field**
```
I'm targeting data science and ML engineering roles at tech companies, not biotech.
Update companies.yaml with relevant companies and tune the keyword filters for my field.
```

**Day-to-day use**
```
I have new jobs from the Chrome extension. Import them, score them, and draft
applications for anything scoring 7 or above.
```
```
Draft an application for job ID 42. My target relocation city for this role is Seattle.
```

**Debugging**
```
My scores all seem too low — most roles I think are good fits are coming back as 5 or 6.
Help me diagnose and improve the scoring profile.
```

To check what's set up at any time without Claude:
```bash
python3 scripts/check_setup.py
```

Otherwise, follow the manual setup steps below.

---

## Prerequisites

1. **Python 3.8 or newer** — check with `python3 --version` in a terminal
2. **pandoc** — converts your resume markdown to DOCX and PDF
   - Mac: `brew install pandoc`
   - Linux/WSL: `sudo apt install pandoc`
   - Windows: download from [pandoc.org/installing.html](https://pandoc.org/installing.html)
3. **An Anthropic API key** — used by the scoring and drafting scripts (`score_auto.py`, `draft.py`).
   Note: this is separate from a Claude Code subscription. Claude Code (the CLI) uses your
   Claude.ai subscription and does not require an API key — but the pipeline scripts call
   the Anthropic Python SDK directly and need `ANTHROPIC_API_KEY` set in your environment.
   Get one at [console.anthropic.com](https://console.anthropic.com/). If you already run
   Claude Code via an API key (not a subscription), that same key works here automatically.
   Costs a few cents per application (see [Cost estimate](#cost-estimate)).
4. **Google Chrome** — for the job-capture extension
5. **Two resume DOCX files** — your resume in Word format, used for styling. See Step 5.

---

## Setup (one-time)

### Step 1 — Install dependencies

```bash
cd ~/projects/job-search-agent
pip install -r requirements.txt
python3 scripts/db.py        # creates data/jobs.db
```

If `pip` isn't found, try `pip3`. If you get permission errors, add `--user`.

### Step 2 — Set your Anthropic API key

The pipeline's scoring and drafting scripts use the Anthropic Python SDK, which reads
`ANTHROPIC_API_KEY` from your environment. This is **separate from Claude Code** — even
if you use Claude Code via a Claude.ai subscription, the scripts still need their own key.

Get a key at [console.anthropic.com](https://console.anthropic.com/), then:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

To make this permanent (so you don't need to set it every session):
- **bash**: `echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc`
- **zsh**: `echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc`

> **Already using Claude Code with an API key?** If you launched Claude Code with
> `ANTHROPIC_API_KEY` set (rather than through a Claude.ai subscription), that same
> key is picked up automatically — no extra step needed.

### Step 3 — Install the Chrome extension

The extension is the primary way to capture jobs — install it once and it works on any site.

1. Open Chrome and go to `chrome://extensions/`
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **"Load unpacked"** → select the `chrome_extension/` folder from this repo
4. The extension icon appears in your Chrome toolbar

That's it. See [Using the Chrome extension](#using-the-chrome-extension) below for daily usage.

### Step 4 — Create your user profile

```bash
cp user_profile.example.yaml user_profile.yaml
```

Open `user_profile.yaml` in any text editor. The file has comments on every field.
Key sections to fill in:

- **Identity**: name, email, phone, location, LinkedIn/GitHub links
- **`windows_downloads`**: path to your Downloads folder (used by the Chrome extension import)
  - WSL: `/mnt/c/Users/YourWindowsName/Downloads`
  - Mac/Linux: `/home/youruser/Downloads` or `/Users/youruser/Downloads`
- **`scoring_profile`**: 10–20 lines describing your background and honest skill gaps.
  This is what Claude reads when deciding whether a job fits you.
- **`draft_profile`**: same but more detailed, including explicit rules about what
  Claude must never claim (e.g., tools you haven't used)
- **`disallowed_patterns`**: blocks specific false claims from appearing in generated
  materials — useful for preventing the AI from blending facts across different projects

### Step 5 — Write your resume sections

```bash
cp draft_all.example.py scripts/draft_all.py
```

Open `scripts/draft_all.py` and replace the placeholder text with your actual resume
content. The file has detailed comments throughout. Key parts:

- **`HEADER`**: your name and contact block (top of every resume)
- **`SKILLS_COMP_REF` / `SKILLS_EXP_REF`**: two versions of your skills section
  (technical-first vs. hands-on-first — the pipeline picks the better one per job)
- **Experience sections**: one constant per project or role; describe accomplishments
  with specific outcomes and methods
- **`SECTION_MAP`**: maps section name strings to your constants
- **`build_resume()`**: assembles the full resume — usually no changes needed here

### Step 6 — Add your resume template files

The pipeline needs two DOCX files in the project root for formatting (fonts, margins):

- `reference_resume_comp.docx` — your resume with technical skills listed first
- `referece_resume_exp.docx` — same but with hands-on/experimental skills first
  *(note: the typo in the second filename is intentional — the code expects it)*

If you only have one resume file, copy it with both names. If starting from scratch:
```bash
python3 scripts/build_reference_docx.py
```

### Step 7 — Configure target companies

Open `data/companies.yaml`. The file already includes many biotech/pharma companies
as an example. Customize it for your search:

**Adding a company:**
```yaml
- name: Company Name
  careers_url: https://company.com/careers
  ats: greenhouse           # greenhouse | lever | ashby | manual
  board_token: companyname  # from their ATS URL (see below)
```

Finding the board token:
- Greenhouse careers URL: `https://boards.greenhouse.io/companyname` → token is `companyname`
- Lever: `https://jobs.lever.co/companyname` → token is `companyname`
- Ashby: `https://jobs.ashbyhq.com/companyname` → token is `companyname`
- No public API → use `ats: manual` (shows as a reminder; not auto-scraped)

**Customizing filters** (bottom of `companies.yaml`):
- **`keywords`**: terms that must appear in the title OR description to include a posting
- **`title_keywords`**: must appear in the title specifically (prevents off-target matches
  at large companies with many unrelated departments)
- **`exclude_locations`**: skip postings in certain cities/countries
- **`exclude_keywords`**: phrases that mean no visa sponsorship — adjust for your situation

### Step 8 — Verify everything

```bash
python3 scripts/check_setup.py
```

All checks should pass before using the pipeline. Fix any flagged issues, then run
your first scrape:
```bash
python3 scripts/scrape_ats.py
```

---

## Using the Chrome extension

The extension is the fastest way to capture jobs since it works on **any website** —
LinkedIn, company career pages, job boards, anywhere.

### Capturing a job

1. Navigate to a job posting in Chrome
2. Click the **Job Scraper** icon in your toolbar
3. The extension reads the page title, company, location, and full description
4. Click **"Save Job"** — it appends to `jobs_scraped.json` in your Downloads folder

You can capture many jobs in one browsing session — each click appends to the same file.

### Importing captured jobs

After a browsing session, import everything at once:

```bash
python3 scripts/import_scraped_jobs.py
```

This reads `jobs_scraped.json` from your Downloads folder, runs each job through the
location/sponsorship filters, inserts new ones into the database, and archives the
file so it won't be double-imported next time.

Then score the new jobs:
```bash
python3 scripts/score_auto.py
```

### Tips for capturing jobs effectively

- **Don't filter yourself** while browsing — capture anything that looks plausible.
  Let the AI scoring (step 2) decide what's worth pursuing. A job that seems like a stretch
  might score higher than expected once the model reads the full description.
- **Capture the full job page**, not a search results page. Navigate into the actual
  posting so the extension can read the complete description.
- **LinkedIn: always open the full post and wait for it to render before clicking Save.**
  LinkedIn loads job descriptions asynchronously — if you click the extension too quickly,
  it may capture an empty or partial description. The steps:
  1. Click the job title to open it (in a new tab, not the side panel)
  2. Wait for the full description to appear on screen — scroll down to confirm it has loaded
  3. *Then* click the extension icon and Save
- The extension works on any page — if a job page looks like it captured incomplete text,
  reload the page, let it fully render, and capture again.

---

## Daily workflow

```bash
cd ~/projects/job-search-agent

# Option A: browse jobs in Chrome, capture with extension, then import
python3 scripts/import_scraped_jobs.py

# Option B: pull new postings from ATS boards automatically
python3 scripts/scrape_ats.py

# Score all new jobs
python3 scripts/score_auto.py --dry-run    # preview first
python3 scripts/score_auto.py              # score for real

# Draft applications for promising jobs (check IDs from score output)
python3 scripts/draft.py 42
python3 scripts/draft.py 42 43 44          # batch
python3 scripts/draft.py 42 --force        # overwrite an existing draft

# Validate generated files for accuracy
python3 scripts/validate.py

# Record a submission
python3 scripts/submit.py 42 --platform "Greenhouse" --notes "referral from Jane"

# Check follow-ups due today
python3 scripts/followup.py
```

---

## Finding job IDs

Each job gets a numeric ID when it enters the database. To see them:

```bash
python3 scripts/edit_job.py      # lists all jobs with IDs, scores, and status
```

The score output also prints IDs after scoring completes.

---

## Tracking submitted applications

After submitting:
1. Run `python3 scripts/submit.py <job_id>` to log it in the database
2. Rename the application folder by prepending `0.` — e.g., rename
   `8_Acme_Scientist` → `0.8_Acme_Scientist`

The `0.x_` prefix tells all scripts this folder is submitted and should never be
overwritten or deleted.

---

## Adding jobs manually

For jobs you find without the Chrome extension:

```bash
python3 scripts/edit_job.py      # interactive prompt to add or edit a job
```

Or import from a LinkedIn JSON export:
```bash
python3 scripts/import_linkedin_json.py data/your_export.json
```

---

## Project structure

```
job-search-agent/
├── scripts/
│   ├── check_setup.py         # setup status checker — run this first
│   ├── config.py              # shared filter logic (location, visa keywords)
│   ├── db.py                  # local SQLite database
│   ├── scrape_ats.py          # bulk-scrapes Greenhouse/Lever/Ashby APIs
│   ├── import_scraped_jobs.py # imports Chrome extension JSON export
│   ├── import_linkedin_json.py
│   ├── parse_saved_pages.py
│   ├── edit_job.py            # add or edit jobs manually
│   ├── score_auto.py          # AI scoring (Claude Haiku)
│   ├── draft.py               # AI drafting (Claude Sonnet)
│   ├── draft_all.py           # YOUR resume content — gitignored
│   ├── docx_builder.py        # builds DOCX from markdown
│   ├── validate.py            # checks generated files for accuracy violations
│   ├── submit.py              # records submissions
│   └── followup.py            # follow-up reminders
├── chrome_extension/          # Chrome extension for capturing job postings
├── data/
│   ├── companies.yaml         # target companies and keyword/location filters
│   └── jobs.db                # your job database (gitignored)
├── applications/              # generated resumes/cover letters (gitignored)
├── user_profile.yaml          # YOUR profile — gitignored
├── user_profile.example.yaml  # template to copy and fill in
├── draft_all.example.py       # resume section skeleton to copy and customize
├── reference_resume_comp.docx # YOUR formatting template (gitignored)
├── referece_resume_exp.docx   # YOUR formatting template (gitignored)
└── requirements.txt
```

---

## Troubleshooting

**Run `python3 scripts/check_setup.py` first** — it identifies the most common issues
and tells you exactly how to fix each one.

| Error | Fix |
|-------|-----|
| `user_profile.yaml not found` | `cp user_profile.example.yaml user_profile.yaml` then fill it in |
| `ModuleNotFoundError: No module named 'anthropic'` | `pip install -r requirements.txt` |
| `pandoc: command not found` | `sudo apt install pandoc` (Linux/WSL) or `brew install pandoc` (Mac) |
| `FileNotFoundError: reference_resume_comp.docx` | Add your DOCX files to the project root, or run `python3 scripts/build_reference_docx.py` |
| `draft_all` import error | `cp draft_all.example.py scripts/draft_all.py` then customize it |
| `jobs_scraped.json not found` | The extension hasn't saved any jobs yet, or `windows_downloads` path is wrong in `user_profile.yaml` |
| Scraped 0 new jobs | All postings already in DB, or no postings match your keyword filters — broaden `keywords` in `companies.yaml` |
| Score unexpectedly low/high | Improve `scoring_profile` in `user_profile.yaml`; also tune the `RUBRIC` in `score_auto.py` |

---

## Cost estimate

| Operation | Model | Approx. cost |
|-----------|-------|--------------|
| Score one job | Claude Haiku | ~$0.001 |
| Draft resume + cover letter | Claude Sonnet | ~$0.02–0.05 |

Scoring 50 new jobs ≈ $0.05. Drafting 10 applications ≈ $0.20–0.50.

---

## License

MIT
