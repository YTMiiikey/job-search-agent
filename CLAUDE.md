# Job Search Agent — Claude Code Instructions

## CRITICAL: Do not create new one-off pipeline scripts

The pipeline has unified scripts for every step. **Never create a new `draft_*.py`,
`score_*.py`, or `rescore_*.py` file.**

When asked to draft an application, always use:
```
python3 scripts/draft.py <job_id>
```

When asked to score jobs, always use:
```
python3 scripts/score_auto.py [--ids N ...] [--dry-run]
```

---

## Pipeline overview

```
scrape  →  score  →  draft  →  submit  →  follow-up
```

| Step | Command |
|------|---------|
| Scrape ATS | `python3 scripts/scrape_ats.py` |
| Import from Chrome extension | `python3 scripts/import_scraped_jobs.py` |
| Manually add/edit a job | `python3 scripts/edit_job.py [--id N]` |
| Auto-score new jobs | `python3 scripts/score_auto.py [--dry-run]` |
| Draft one or more jobs | `python3 scripts/draft.py <job_id> [<job_id> ...]` |
| Record a submission | `python3 scripts/submit.py <job_id> [--platform STR] [--notes STR]` |
| View follow-up reminders | `python3 scripts/followup.py` |
| Validate all applications | `python3 scripts/validate.py` |

---

## Submitted applications

Folders prefixed `0.x_` (e.g. `0.9_Acme_ScientistComputationalBiology`) are
**already submitted**. The user renames them manually to mark submission.
**Never delete or modify these folders.**

---

## Content accuracy

All accuracy constraints live in `user_profile.yaml` under `disallowed_patterns`.
`validate.py` loads them at runtime. Run `python3 scripts/validate.py` to scan
all non-submitted folders for violations before submitting.

The LLM is also given the candidate's full `draft_profile` from `user_profile.yaml`,
which should include explicit "NEVER do X" rules for anything that must not appear
in generated materials.

---

## SUMMARY section: bullet-pool selection only — never free-form write

Build the SUMMARY from the fixed bullet pool defined in the source template
DOCX files and `draft_all.py`. Do not write new sentences or merge facts from
two different bullets. Each summary bullet must trace back to a single,
verifiable source bullet in the candidate's actual experience.

---

## Two resume templates

| Template | File | Skills order | When to use |
|----------|------|-------------|-------------|
| COMP | `reference_resume_comp.docx` | Technical/computational first | Technical/ML-heavy JDs |
| EXP | `referece_resume_exp.docx` | Experimental/hands-on first | Lab/experimental-heavy JDs |

`draft.py` selects automatically. Override by editing the `template` field in the result dict.

---

## Experience section keys

Defined in `draft_all.py` and documented in `draft_all.example.py`. The LLM
chooses a subset per JD based on the available keys described in the prompt.

---

## Database

`data/jobs.db` — SQLite. Status flow: `new → scored → drafted → submitted`

Key functions in `scripts/db.py`: `get_jobs()`, `update_status()`,
`record_submission()`, `get_followups_due()`

The `submissions` table tracks platform, notes, follow-up due date, and outcome.

---

## Folder naming convention

All application folders: `{score}_{CompanySlug}_{RoleSlug}`

`draft.py` auto-generates the folder name. Do not rename existing drafted folders —
only the user renames them to `0.x_` upon submission.

---

## Adding a new company to scrape

Edit `data/companies.yaml`. Add an entry under `companies:` with `name`,
`careers_url`, `ats` (greenhouse/lever/ashby/manual), and `board_token`.
Then run `scrape_ats.py`.

---

## Personal configuration

All personal info (name, contact, career profile, accuracy rules, file paths) is
in `user_profile.yaml` (gitignored). See `user_profile.example.yaml` for the
full template and field descriptions.

Your actual resume content (experience sections, publication list, etc.) lives in
`scripts/draft_all.py` (also gitignored). See `draft_all.example.py` for the
expected structure.
