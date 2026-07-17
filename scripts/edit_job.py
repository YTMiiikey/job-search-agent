"""
Interactive CLI to manually view and edit any job row in jobs.db.
Useful for pasting in a job description copied from a LinkedIn page.

Usage:
    python scripts/edit_job.py              # list all 'new' jobs
    python scripts/edit_job.py --id 60      # edit a specific job by id
    python scripts/edit_job.py --status all # list jobs of any status
"""

import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db

EDITABLE = ["company", "title", "location", "description", "status", "fit_score", "fit_rationale"]


def list_jobs(status_filter):
    db.init_db()
    conn = db.get_connection()
    if status_filter == "all":
        rows = conn.execute("SELECT id, company, title, status, fit_score FROM jobs ORDER BY id").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, company, title, status, fit_score FROM jobs WHERE status=? ORDER BY id",
            (status_filter,)
        ).fetchall()
    conn.close()
    if not rows:
        print("No jobs found.")
        return
    print(f"{'ID':>4}  {'Company':20}  {'Title':50}  {'Status':10}  Score")
    print("-" * 100)
    for r in rows:
        print(f"{r[0]:>4}  {(r[1] or ''):20}  {(r[2] or ''):50}  {r[3]:10}  {r[4] or ''}")


def edit_job(job_id):
    db.init_db()
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        print(f"No job with id={job_id}")
        conn.close()
        return
    cols = [d[0] for d in conn.execute("SELECT * FROM jobs LIMIT 0").description]
    conn.close()

    job = dict(zip(cols, row))
    print(f"\n=== Job id={job_id} ===")
    for col in cols:
        val = job[col]
        preview = (str(val)[:120] + "…") if val and len(str(val)) > 120 else val
        print(f"  {col}: {preview}")

    print(f"\nEditable fields: {', '.join(EDITABLE)}")
    print("Enter  field=value  to update (multi-line values: type field=  then paste, end with a line containing just '.')")
    print("Press Enter with no input to finish.\n")

    updates = {}
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        if "=" not in line:
            print("  Format: field=value")
            continue
        field, _, value = line.partition("=")
        field = field.strip().lower()
        if field not in EDITABLE:
            print(f"  Unknown field '{field}'. Choose from: {', '.join(EDITABLE)}")
            continue
        if value == "":
            # Multi-line mode
            print(f"  Paste {field} (end with a line containing just '.'):")
            lines = []
            while True:
                try:
                    l = input()
                except EOFError:
                    break
                if l == ".":
                    break
                lines.append(l)
            value = "\n".join(lines)
        updates[field] = value.strip()
        print(f"  Staged: {field} = {value[:80]!r}{'…' if len(value)>80 else ''}")

    if not updates:
        print("No changes.")
        return

    conn = db.get_connection()
    set_clause = ", ".join(f"{f}=?" for f in updates)
    conn.execute(f"UPDATE jobs SET {set_clause} WHERE id=?", [*updates.values(), job_id])
    conn.commit()
    conn.close()
    print(f"\nUpdated job id={job_id}: {', '.join(updates.keys())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, help="Job ID to edit")
    parser.add_argument("--status", default="new",
                        help="Status filter for listing (default: new, use 'all' for everything)")
    args = parser.parse_args()

    if args.id:
        edit_job(args.id)
    else:
        list_jobs(args.status)


if __name__ == "__main__":
    main()
