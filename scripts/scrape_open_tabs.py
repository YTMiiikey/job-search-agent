"""
Scrape all open job-posting tabs from Chrome.

Runs the native Windows PowerShell CDP scraper (scripts/chrome_scrape.ps1),
reads the JSON output, and upserts results into jobs.db.

Usage:
    python3 scripts/scrape_open_tabs.py

Chrome does NOT need to be launched specially — the PowerShell script handles
that automatically if it isn't already running with the debug port.
"""

import json, re, subprocess, sys, tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PS1  = ROOT / "scripts" / "chrome_scrape.ps1"

sys.path.insert(0, str(ROOT / "scripts"))
import db
from config import classify_job


def run_powershell_scraper():
    # Write results to Windows Temp so PS1 can write and we can read it back
    win_tmp = r"C:\Windows\Temp\job_scrape_results.json"
    wsl_tmp = Path("/mnt/c/Windows/Temp/job_scrape_results.json")

    ps1_win = str(Path(subprocess.check_output(
        ["wslpath", "-w", str(PS1)], text=True).strip()))

    print("Running Chrome scraper via PowerShell...")
    result = subprocess.run(
        ["powershell.exe", "-ExecutionPolicy", "Bypass",
         "-File", ps1_win, "-OutFile", win_tmp],
        text=True
    )

    if not wsl_tmp.exists():
        print("[!] PowerShell scraper produced no output file.")
        return []

    data = json.loads(wsl_tmp.read_text(encoding="utf-8"))
    wsl_tmp.unlink(missing_ok=True)

    # ConvertTo-Json wraps a single item as object, not array
    if isinstance(data, dict):
        data = [data]
    return data or []


def upsert(job: dict):
    db.init_db()
    conn = db.get_connection()

    url         = (job.get("url")         or "").strip()
    company     = (job.get("company")     or "").strip()
    title       = (job.get("title")       or "").strip()
    location    = (job.get("location")    or "").strip()
    description = (job.get("description") or "").strip()

    if not title:
        conn.close()
        return None, "skipped (no title)"

    # Warn if description looks like a login wall
    if description and len(description) < 300:
        print(f"  [!] Description very short ({len(description)} chars) — may be a login wall")

    existing = None
    if url:
        existing = conn.execute("SELECT id FROM jobs WHERE url=?", (url,)).fetchone()
    if not existing and title:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE title=? AND (company=? OR company IS NULL OR company='')",
            (title, company)
        ).fetchone()

    if existing:
        job_id = existing[0]
        conn.execute("""
            UPDATE jobs SET
                company     = CASE WHEN ? != '' THEN ? ELSE company END,
                location    = CASE WHEN ? != '' THEN ? ELSE location END,
                description = CASE WHEN ? != '' THEN ? ELSE description END
            WHERE id=?
        """, (company, company, location, location, description, description, job_id))
        conn.commit()
        conn.close()
        return job_id, "updated"
    else:
        effective_url = url or f"scraped://{re.sub(r'[^a-z0-9]', '-', title.lower())[:60]}"
        status, fit_rationale = classify_job(title, description, location)
        conn.execute(
            "INSERT OR IGNORE INTO jobs "
            "(source, company, title, location, url, description, date_found, status, fit_rationale) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            ("chrome_tab", company, title, location, effective_url,
             description, date.today().isoformat(), status, fit_rationale)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM jobs WHERE url=?", (effective_url,)).fetchone()
        conn.close()
        return (row[0] if row else None), "inserted"


def main():
    jobs = run_powershell_scraper()
    if not jobs:
        print("No job data returned.")
        return

    print(f"\nProcessing {len(jobs)} job(s)...\n")
    for job in jobs:
        title = job.get("title", "")[:70]
        company = job.get("company", "")
        desc_len = len(job.get("description", ""))
        job_id, action = upsert(job)
        print(f"[{action:8}] id={job_id}  {company} — {title}  ({desc_len} chars)")

    print(f"\nDone. Ask Claude Code to 'process new jobs' to score and draft applications.")


if __name__ == "__main__":
    main()
