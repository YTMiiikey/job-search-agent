# Job Search Agent

An AI-powered job search pipeline for scientific and technical roles. It automatically
finds job postings, scores them against your background, and writes tailored resumes and
cover letters — all running locally on your machine.

Designed for researchers and scientists in biotech, pharma, computational biology, and
adjacent fields. Configurable for any technical or scientific job search.

---

## What it does

```
scrape → score → draft → submit → follow-up
```

| Step | What happens |
|------|-------------|
| **Scrape** | Fetches new postings from company career portals (Greenhouse/Lever/Ashby APIs) automatically, or imports from a Chrome extension when you browse job pages manually |
| **Score** | Sends each posting to Claude AI with your background summary; assigns a 1–9 fit score and saves a brief rationale to a local database |
| **Draft** | For jobs worth applying to, Claude generates a tailored resume summary and cover letter; pandoc converts them to DOCX and PDF |
| **Submit** | Records your submissions with the platform used, notes, and a follow-up date |
| **Follow-up** | Shows you which applications need a follow-up today |

All generated files (resumes, cover letters) stay on your machine and are never uploaded anywhere except the Anthropic API for generation.

---

## Prerequisites

You need four things before you can use this:

1. **Python 3.8 or newer** — check with `python3 --version` in a terminal
2. **pandoc** — converts your resume markdown to DOCX and PDF
   - Mac: `brew install pandoc`
   - Linux/WSL: `sudo apt install pandoc`
   - Windows: download from [pandoc.org/installing.html](https://pandoc.org/installing.html)
3. **An Anthropic API key** — used for scoring and drafting. Sign up at [console.anthropic.com](https://console.anthropic.com/). API calls cost a small amount per job (scoring ~$0.001 per job with Haiku, drafting ~$0.01–0.05 per resume with Sonnet).
4. **Two resume template DOCX files** — your existing resume in Word format, which the pipeline uses for styling (margins, fonts). See Step 5 below.

---

## Setup (one-time)

### Step 1 — Download and install dependencies

```bash
# Clone or download this repository, then navigate into it
cd ~/projects/job-search-agent

# Install Python packages
pip install -r requirements.txt

# Initialize the database (creates data/jobs.db)
python3 scripts/db.py
```

If `pip` isn't found, try `pip3`. If you get permission errors, add `--user` after `pip install`.

### Step 2 — Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

To make this permanent so you don't have to set it every session, add the line to your
shell startup file:
- **bash**: `echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.bashrc`
- **zsh**: `echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc`

### Step 3 — Create your user profile

```bash
cp user_profile.example.yaml user_profile.yaml
```

Open `user_profile.yaml` in any text editor and fill in your details. The file has
comments explaining each field. The most important sections:

- **Identity**: your name, email, phone, and links
- **`scoring_profile`**: 10–20 lines describing your background, skills, and honest
  skill gaps. This is what Claude reads when deciding whether a job fits you.
- **`draft_profile`**: same as above but more detailed, with explicit rules about what
  Claude must never fabricate in your resume (e.g., tools you haven't used)
- **`disallowed_patterns`**: regular expressions that block specific false claims from
  appearing in generated materials — useful for preventing the AI from blending facts
  from different parts of your experience

### Step 4 — Write your resume sections

```bash
cp draft_all.example.py scripts/draft_all.py
```

Open `scripts/draft_all.py` and replace the placeholder text with your actual resume
content. Each constant you define becomes an experience section Claude can include in
tailored resumes.

The file has detailed comments explaining every piece. Key things to customize:

- **`HEADER`**: your name and contact block (appears at the top of every resume)
- **`SKILLS_COMP_REF` / `SKILLS_EXP_REF`**: two versions of your skills section
  (technical-first vs. hands-on-first)
- **Experience sections**: one constant per project or role; name them clearly since
  Claude uses these names to choose what to include
- **`SECTION_MAP`**: the dict that maps section names (strings) to your constants
- **`build_resume()`**: assembles the full resume from a summary + skills + sections

### Step 5 — Add your resume template files

The pipeline needs two DOCX files in the project root to control formatting
(margins, fonts, heading styles):

- `reference_resume_comp.docx` — your resume with technical/computational skills listed first
- `referece_resume_exp.docx` — your resume with experimental/hands-on skills listed first

These are usually the same file or minor variations. The pipeline replaces the content
but keeps the styling. If you only have one resume template, copy it twice with both names.

**Note**: The second filename has a typo (`referece` not `reference`) — this is intentional
and must stay this way so the code can find it.

To create a reference DOCX from scratch if you don't have one:
```bash
python3 scripts/build_reference_docx.py
```

### Step 6 — Add companies to scrape

Open `data/companies.yaml` and look at the `companies:` section. Each entry has:

```yaml
- name: Company Name
  careers_url: https://company.com/careers
  ats: greenhouse           # one of: greenhouse, lever, ashby, manual
  board_token: companyname  # the token in their ATS URL
```

To find a company's board token, visit their careers page and look at the URL:
- Greenhouse: `https://boards.greenhouse.io/companyname` → token is `companyname`
- Lever: `https://jobs.lever.co/companyname` → token is `companyname`
- Ashby: `https://jobs.ashbyhq.com/companyname` → token is `companyname`

Companies without a public API → set `ats: manual` (they appear in your list as reminders
to check manually, but won't be auto-scraped).

Also customize the filter keywords at the bottom of `companies.yaml`:
- **`keywords`**: terms that must appear in a posting's title OR description to include it
- **`title_keywords`**: terms that must appear in the title specifically (prevents broad
  keyword matches from pulling in unrelated roles at large companies)
- **`exclude_locations`**: cities/countries to skip (e.g., if you're US-only)
- **`exclude_keywords`**: phrases indicating no visa sponsorship (adjust for your situation)

---

## Daily usage

```bash
cd ~/projects/job-search-agent

# 1. Check for new postings (takes ~30 seconds)
python3 scripts/scrape_ats.py

# 2. Score new jobs — preview first, then run for real
python3 scripts/score_auto.py --dry-run    # shows what would be scored
python3 scripts/score_auto.py              # scores and saves to DB

# 3. Draft applications for promising jobs (score >= 5 or so)
python3 scripts/draft.py 42               # draft one job by its DB ID
python3 scripts/draft.py 42 43 44         # draft several at once
python3 scripts/draft.py 42 --force       # re-draft an existing application

# 4. Check for accuracy issues in generated files
python3 scripts/validate.py

# 5. Record a submission
python3 scripts/submit.py 42 --platform "Greenhouse" --notes "referred by Jane"

# 6. See follow-ups due today
python3 scripts/followup.py
```

To see all available jobs in the database and their scores:
```bash
python3 scripts/edit_job.py
```

---

## Finding job IDs

After scoring, the DB assigns each job a numeric ID. To see them:

```bash
python3 scripts/edit_job.py           # lists all jobs with IDs and scores
python3 scripts/score_auto.py         # also prints IDs and scores when done
```

---

## Tracking submitted applications

After you submit an application:
1. Run `python3 scripts/submit.py <job_id>` to record it in the DB
2. Rename the application folder from e.g. `8_Acme_Scientist` to `0.8_Acme_Scientist`
   (add `0.` prefix) — this signals to all scripts that it's submitted and should not
   be overwritten

Scripts skip folders with the `0.x_` prefix and never delete or modify them.

---

## Adding jobs manually

If you find a job that isn't on a supported ATS:

```bash
python3 scripts/edit_job.py           # opens an interactive prompt to add/edit a job
```

Or import from a LinkedIn job export:
```bash
python3 scripts/import_linkedin_json.py data/your_export.json
```

---

## Chrome extension

The extension in `chrome_extension/` lets you capture job details from any page you're
browsing (useful for jobs on company websites, LinkedIn, etc.).

**Installation**:
1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked" → select the `chrome_extension/` folder
4. Visit a job posting → click the extension icon → save the job

The extension saves a `jobs_scraped.json` file to your Downloads folder. Import it with:
```bash
python3 scripts/import_scraped_jobs.py
```

On Windows/WSL: make sure `windows_downloads` in `user_profile.yaml` points to your
Windows Downloads folder (e.g., `/mnt/c/Users/YourName/Downloads`).

---

## Project structure

```
job-search-agent/
├── scripts/
│   ├── config.py              # shared filter logic (location, visa keywords)
│   ├── db.py                  # local SQLite database
│   ├── scrape_ats.py          # auto-scrapes Greenhouse/Lever/Ashby APIs
│   ├── import_scraped_jobs.py # imports Chrome extension JSON
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
├── chrome_extension/          # browser extension for manual job capture
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

**`user_profile.yaml not found`**
→ Run `cp user_profile.example.yaml user_profile.yaml` and fill in your details.

**`ModuleNotFoundError: No module named 'anthropic'`**
→ Run `pip install -r requirements.txt` (or `pip3 install -r requirements.txt`).

**`pandoc: command not found`**
→ Install pandoc: `sudo apt install pandoc` (Linux/WSL) or `brew install pandoc` (Mac).

**`FileNotFoundError: reference_resume_comp.docx`**
→ Add your resume DOCX files to the project root, or run `python3 scripts/build_reference_docx.py` to generate a blank template.

**`draft_all` import error**
→ Run `cp draft_all.example.py scripts/draft_all.py` and customize it with your resume content.

**Score is unexpectedly low/high**
→ Improve your `scoring_profile` in `user_profile.yaml` — be more specific about your strongest
skills and honest about gaps. Also review the `RUBRIC` in `scripts/score_auto.py` and adjust
the scoring anchors for your target seniority level and field.

**Scraped 0 new jobs**
→ All matched postings are already in your DB, or no postings matched your keyword filters.
Add more companies to `data/companies.yaml` or broaden your `keywords` list.

---

## Cost estimate

| Operation | Model | Cost per call |
|-----------|-------|--------------|
| Score one job | Claude Haiku | ~$0.001 |
| Draft resume + cover letter | Claude Sonnet | ~$0.02–0.05 |

Scoring 50 new jobs ≈ $0.05. Drafting 10 applications ≈ $0.20–0.50.

---

## License

MIT
