#!/usr/bin/env python3
"""Auto-score 'new' jobs using Claude API.

Usage:
    # Score all jobs with status='new' (dry-run preview first)
    python3 scripts/score_auto.py

    # Score specific job IDs
    python3 scripts/score_auto.py --ids 280 281 282

    # Dry run: show what would be scored without calling the API
    python3 scripts/score_auto.py --dry-run

    # Re-score already-scored jobs (careful: overwrites existing scores)
    python3 scripts/score_auto.py --rescore

Each job is sent to Claude with the candidate's profile summary and a 1-9 scoring
rubric. The API response is parsed for {score, rationale} and written to
the DB (fit_score, fit_rationale, status → 'scored').
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db
from config import load_profile

# Loaded lazily at first use so --dry-run works without a profile.
def _get_profile() -> str:
    return load_profile()["scoring_profile"]

# ── Scoring rubric ─────────────────────────────────────────────────────────
# Customize anchors and deductions to match your target field and seniority.
RUBRIC = """
Score 1–9. Use these anchors:

9 — Near-perfect fit. Strong match on ≥4 core skills, target seniority level,
    relevant domain, US location, no visa/clearance blockers.

8 — Very strong. Strong overlap on ≥3 core skills, only minor gaps.

7 — Strong. Good overlap but one meaningful gap (missing a key tool/method,
    slight seniority stretch, or tangential sub-domain).

6 — Moderate. Relevant domain, 2+ skill gaps, or lukewarm seniority fit.
    Worth applying with a tailored letter.

5 — Marginal. Partially relevant domain, several gaps. A clear reach but
    transferable skills make it worth generating a resume.

4 — Weak-but-possible. Some skill overlap but notable domain mismatch.
    Keep on radar; apply only if pipeline is thin.

3 — Poor. Wrong domain, missing 4+ core skills, or mostly non-transferable.

2 — Very poor. Off-domain or seniority way out of range.

1 — Irrelevant. Completely off-domain.

Additional deductions:
- Contract/temp role: −1
- Requires US citizenship / security clearance: −2 (or mark exclude_sponsorship)
- Role is purely non-technical (ops, clinical, admin) with only minor science component: −2
""".strip()

SYSTEM_PROMPT = f"""You are scoring job postings for fit with a specific candidate's profile.
Respond ONLY with a JSON object — no explanation, no markdown fences.

{{'score': <integer 1-9>, 'rationale': '<2-4 sentences summarizing fit and key gaps>'}}

The rationale must be specific: name the company and role, mention 2-3 matching skills,
and call out 1-2 gaps or concerns. Max 100 words."""

USER_TEMPLATE = """Candidate profile:
{profile}

Scoring rubric:
{rubric}

Job to score:
Company: {company}
Title: {title}
Location: {location}

Job description (first 3000 chars):
{description}

Respond with JSON only: {{"score": N, "rationale": "..."}}"""


def score_job(client, job: dict) -> tuple[int, str]:
    """Call Claude API for one job. Returns (score, rationale)."""
    desc = (job.get("description") or "")[:3000]
    user_msg = USER_TEMPLATE.format(
        profile=_get_profile(),
        rubric=RUBRIC,
        company=job.get("company", ""),
        title=job.get("title", ""),
        location=job.get("location", ""),
        description=desc,
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text.strip()
    parsed = json.loads(text)
    return int(parsed["score"]), str(parsed["rationale"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-score new jobs via Claude API")
    parser.add_argument("--ids", nargs="+", type=int, help="Score specific job IDs only")
    parser.add_argument("--dry-run", action="store_true", help="Preview jobs without calling API")
    parser.add_argument("--rescore", action="store_true",
                        help="Re-score jobs already in 'scored' status")
    parser.add_argument("--delay", type=float, default=0.5,
                        help="Seconds between API calls (default: 0.5)")
    args = parser.parse_args()

    jobs = db.get_jobs()

    if args.ids:
        jobs = [j for j in jobs if j["id"] in args.ids]
    elif args.rescore:
        jobs = [j for j in jobs if j["status"] in ("new", "scored", "drafted")]
    else:
        jobs = [j for j in jobs if j["status"] == "new"]

    if not jobs:
        print("No jobs to score.")
        return

    print(f"{'DRY RUN — ' if args.dry_run else ''}Scoring {len(jobs)} job(s):\n")
    for j in jobs:
        print(f"  [{j['id']}] {j['company']} — {j['title']} ({j['status']})")

    if args.dry_run:
        return

    import anthropic
    client = anthropic.Anthropic()

    scored = 0
    errors = 0
    for job in jobs:
        jid = job["id"]
        label = f"[{jid}] {job['company']} — {job['title']}"
        try:
            score, rationale = score_job(client, job)
            db.update_status(jid, "scored", fit_score=score, fit_rationale=rationale)
            print(f"  {label}  →  {score}/9")
            print(f"    {rationale}")
            scored += 1
        except Exception as e:
            print(f"  ERROR {label}: {e}", file=sys.stderr)
            errors += 1
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"\nDone. {scored} scored, {errors} errors.")
    if scored:
        conn = db.get_connection()
        rows = conn.execute(
            "SELECT id, fit_score, company, title FROM jobs "
            "WHERE status='scored' ORDER BY fit_score DESC LIMIT 10"
        ).fetchall()
        conn.close()
        print("\nTop scored jobs:")
        for r in rows:
            print(f"  {r[1]}/9  [{r[0]}] {r[2]} — {r[3]}")


if __name__ == "__main__":
    main()
