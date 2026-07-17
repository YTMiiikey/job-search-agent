#!/usr/bin/env python3
"""Show submissions due for follow-up and let you update outcomes.

Usage:
    # List all submissions due for follow-up today or overdue
    python3 scripts/followup.py

    # List all submissions regardless of due date
    python3 scripts/followup.py --all

    # Mark a submission's outcome
    python3 scripts/followup.py --update <submission_id> --outcome <outcome>

Outcomes: rejected, offer, interviewing, ghosted, withdrew
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db

VALID_OUTCOMES = {"rejected", "offer", "interviewing", "ghosted", "withdrew"}


def print_submissions(rows: list[dict]) -> None:
    if not rows:
        print("No submissions found.")
        return
    print(f"{'ID':>4}  {'Job ID':>6}  {'Company':<28}  {'Submitted':>10}  {'Follow-up':>10}  {'Outcome':<12}")
    print("─" * 90)
    for r in rows:
        outcome = r["outcome"] or "—"
        print(f"{r['id']:>4}  {r['job_id']:>6}  {r['company']:<28}  "
              f"{r['submitted_at']:>10}  {(r['followup_due'] or '—'):>10}  {outcome:<12}")
        print(f"       {r['title']}")
        if r.get("platform"):
            print(f"       Platform: {r['platform']}")
        if r.get("notes"):
            print(f"       Notes: {r['notes']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage application follow-ups")
    parser.add_argument("--all", action="store_true", help="Show all submissions, not just overdue ones")
    parser.add_argument("--update", type=int, metavar="SUBMISSION_ID",
                        help="Update the outcome for this submission id")
    parser.add_argument("--outcome", choices=list(VALID_OUTCOMES),
                        help="Outcome to set (use with --update)")
    args = parser.parse_args()

    if args.update is not None:
        if not args.outcome:
            print("Error: --outcome is required with --update", file=sys.stderr)
            sys.exit(1)
        conn = db.get_connection()
        conn.execute("UPDATE submissions SET outcome=? WHERE id=?", (args.outcome, args.update))
        conn.commit()
        conn.close()
        print(f"Submission {args.update} updated: outcome = {args.outcome}")
        return

    if args.all:
        rows = db.get_submissions()
    else:
        rows = db.get_followups_due()
        if not rows:
            all_rows = db.get_submissions()
            pending = [r for r in all_rows if r["outcome"] is None]
            print(f"No follow-ups due today. ({len(pending)} pending submissions with no outcome.)")
            return
        print(f"Follow-ups due ({len(rows)} total):\n")

    print_submissions(rows)


if __name__ == "__main__":
    main()
