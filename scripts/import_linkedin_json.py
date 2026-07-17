"""Import LinkedIn jobs from a scraped JSON file into jobs.db.

Usage:
    python scripts/import_linkedin_json.py data/jobs_scraped_jul8.json
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db
from config import classify_job

JSON_PATH = ROOT / "data" / "jobs_scraped_jul8.json"
if len(sys.argv) > 1:
    JSON_PATH = Path(sys.argv[1])


def clean_url(url):
    m = re.search(r'(https://www\.linkedin\.com/jobs/view/\d+)', url)
    return m.group(1) if m else url.split("?")[0]


def main():
    data = json.load(open(JSON_PATH))
    db.init_db()
    conn = db.get_connection()
    today = date.today().isoformat()

    imported = 0
    skipped = 0
    for job in data:
        url = clean_url(job.get("url", ""))
        title = (job.get("title") or "").strip()
        company = (job.get("company") or "").strip()
        location = (job.get("location") or "").strip()
        description = (job.get("description") or "").strip()

        if not title:
            continue

        # Check for existing by URL job ID
        job_id_m = re.search(r"jobs/view/(\d+)", url)
        existing = None
        if job_id_m:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE url LIKE ?", (f"%{job_id_m.group(1)}%",)
            ).fetchone()
        if not existing and title:
            existing = conn.execute(
                "SELECT id FROM jobs WHERE title=? AND company=?", (title, company)
            ).fetchone()

        if existing:
            skipped += 1
            continue

        if not url:
            url = f"linkedin://{title.replace(' ', '_')[:60]}"

        status, fit_rationale = classify_job(title, description, location)
        conn.execute(
            "INSERT INTO jobs (source, company, title, location, url, description, date_found, status, fit_rationale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("linkedin_json", company, title, location, url, description, today, status, fit_rationale),
        )
        imported += 1

    conn.commit()

    print(f"Imported {imported} new jobs, skipped {skipped} already in DB.")
    print("\nNewly imported jobs:")
    rows = conn.execute(
        "SELECT id, company, title FROM jobs WHERE source='linkedin_json' AND status='new' ORDER BY id"
    ).fetchall()
    for r in rows:
        print(f"  id={r[0]:3d}  {r[1]:35}  {r[2][:55]}")

    conn.close()


if __name__ == "__main__":
    main()
