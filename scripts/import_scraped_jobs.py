"""
Import jobs_scraped.json (downloaded by the Chrome extension) into jobs.db.

Usage:
    python3 scripts/import_scraped_jobs.py

Looks for jobs_scraped.json in your Windows Downloads folder automatically.
"""

import json, re, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db
from config import classify_job, load_profile

def _downloads_path() -> Path:
    try:
        p = load_profile().get("windows_downloads", "")
        if p:
            return Path(p)
    except Exception:
        pass
    return Path.home() / "Downloads"

DOWNLOADS = _downloads_path()
JSON_FILE = DOWNLOADS / "jobs_scraped.json"


def upsert(job: dict):
    conn = db.get_connection()

    url         = (job.get("url")         or "").strip()
    company     = (job.get("company")     or "").strip()
    title       = (job.get("title")       or "").strip()
    location    = (job.get("location")    or "").strip()
    description = (job.get("description") or "").strip()

    if not title:
        conn.close()
        return None, "skipped (no title)"

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
            ("chrome_extension", company, title, location, effective_url,
             description, date.today().isoformat(), status, fit_rationale)
        )
        conn.commit()
        row = conn.execute("SELECT id FROM jobs WHERE url=?", (effective_url,)).fetchone()
        conn.close()
        return (row[0] if row else None), "inserted"


def main():
    if not JSON_FILE.exists():
        print(f"[!] {JSON_FILE} not found.")
        print("    Click the Job Scraper extension icon in Chrome to generate it.")
        return

    jobs = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    if isinstance(jobs, dict):
        jobs = [jobs]

    print(f"Found {len(jobs)} job(s) in {JSON_FILE.name}\n")
    db.init_db()

    for job in jobs:
        desc_len = len(job.get("description", ""))
        job_id, action = upsert(job)
        print(f"[{action:8}] id={job_id}  {job.get('company',''):25}  {job.get('title','')[:55]}  ({desc_len} chars)")

    # Archive the file so it's not double-imported next run
    archive = DOWNLOADS / "jobs_scraped_imported.json"
    JSON_FILE.rename(archive)
    print(f"\nArchived to {archive.name}")
    print("Done. Ask Claude Code to 'process new jobs' to score and draft applications.")


if __name__ == "__main__":
    main()
