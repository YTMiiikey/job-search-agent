#!/usr/bin/env python3
"""Record a job application submission in the database.

Usage:
    python3 scripts/submit.py <job_id> [--platform PLATFORM] [--notes TEXT] [--followup-days N]

Examples:
    python3 scripts/submit.py 213
    python3 scripts/submit.py 213 --platform "Greenhouse" --notes "referral from Jane"
    python3 scripts/submit.py 213 --followup-days 7

Updates jobs.status to 'submitted' and inserts a submissions row with a
follow-up due date (default 14 days).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a job submission")
    parser.add_argument("job_id", type=int, help="Job ID from jobs table")
    parser.add_argument("--platform", default=None, help="Where you submitted (e.g. Greenhouse, LinkedIn)")
    parser.add_argument("--notes", default=None, help="Free-text notes (referral, deadline, etc.)")
    parser.add_argument("--followup-days", type=int, default=14,
                        help="Days until follow-up reminder (default: 14)")
    args = parser.parse_args()

    conn = db.get_connection()
    row = conn.execute("SELECT id, company, title, status FROM jobs WHERE id=?",
                       (args.job_id,)).fetchone()
    conn.close()

    if row is None:
        print(f"Error: no job with id={args.job_id}", file=sys.stderr)
        sys.exit(1)

    job_id, company, title, status = row
    if status == "submitted":
        print(f"Warning: job {job_id} ({company} — {title}) already marked submitted.")

    sub_id = db.record_submission(
        job_id=args.job_id,
        platform=args.platform,
        notes=args.notes,
        followup_days=args.followup_days,
    )

    from datetime import date, timedelta
    followup = (date.today() + timedelta(days=args.followup_days)).isoformat()
    print(f"Submitted: [{job_id}] {company} — {title}")
    if args.platform:
        print(f"  Platform: {args.platform}")
    if args.notes:
        print(f"  Notes:    {args.notes}")
    print(f"  Follow-up due: {followup}")
    print(f"  Submission record id: {sub_id}")


if __name__ == "__main__":
    main()
