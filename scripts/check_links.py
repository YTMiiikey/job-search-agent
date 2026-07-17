#!/usr/bin/env python3
"""Check whether job posting URLs are still live.

For native ATS (Greenhouse, Ashby, Lever): a 404 is definitive.
For LinkedIn: check for redirect to non-job pages or "no longer available" body text.

Usage:
    python3 scripts/check_links.py            # report only
    python3 scripts/check_links.py --close    # also mark confirmed-closed jobs as 'closed' in DB
"""

import sys
import time
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 10

# Phrases in the response body (case-insensitive) that strongly indicate a closed posting.
CLOSED_BODY_PHRASES = [
    "job is no longer available",
    "position is no longer available",
    "this job has expired",
    "this position has been filled",
    "no longer accepting applications",
    "posting has been closed",
    "listing has expired",
]

# If the final URL (after redirects) ends up here, the job is gone.
CLOSED_REDIRECT_PATTERNS = [
    "linkedin.com/jobs/view/expired",
    "linkedin.com/jobs/closed",
    "/jobs/?",           # redirected to job search root
    "greenhouse.io/arcinstitute?error=true",
    "greenhouse.io/?error=true",  # Greenhouse generic closed-job redirect
    "?error=true",       # Greenhouse ATS closes jobs by redirecting to board?error=true
]


def check_url(job_id, company, title, url):
    """Return (job_id, company, title, url, verdict, detail) where
    verdict is 'open', 'closed', or 'unknown'."""
    if not url:
        return job_id, company, title, url, "unknown", "no URL"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)

        # Definitive 404 → closed
        if resp.status_code == 404:
            return job_id, company, title, url, "closed", "HTTP 404"

        # 410 Gone
        if resp.status_code == 410:
            return job_id, company, title, url, "closed", "HTTP 410"

        # Check final URL after redirects
        final_url = resp.url.lower()
        for pat in CLOSED_REDIRECT_PATTERNS:
            if pat in final_url:
                return job_id, company, title, url, "closed", f"redirected to {resp.url[:80]}"

        # LinkedIn redirected to login page → we can't tell
        if "linkedin.com/login" in final_url or "linkedin.com/authwall" in final_url:
            return job_id, company, title, url, "unknown", "LinkedIn auth required"

        # Body text checks (only for non-huge pages)
        body = resp.text[:40_000].lower()
        for phrase in CLOSED_BODY_PHRASES:
            if phrase in body:
                return job_id, company, title, url, "closed", f'body contains "{phrase}"'

        return job_id, company, title, url, "open", f"HTTP {resp.status_code}"

    except requests.exceptions.ConnectionError:
        return job_id, company, title, url, "closed", "connection error (domain gone)"
    except requests.exceptions.Timeout:
        return job_id, company, title, url, "unknown", "timeout"
    except Exception as e:
        return job_id, company, title, url, "unknown", str(e)[:60]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--close", action="store_true",
                        help="Mark confirmed-closed jobs as 'closed' in the DB")
    parser.add_argument("--status", default=None,
                        help="Only check jobs with this status (e.g. 'drafted', 'scored')")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of parallel requests (default 8)")
    args = parser.parse_args()

    conn = db.get_connection()
    db.init_db()

    where = "status NOT IN ('exclude_location','exclude_sponsorship','closed')"
    params = ()
    if args.status:
        where += " AND status = ?"
        params = (args.status,)

    rows = conn.execute(
        f"SELECT id, company, title, url, status FROM jobs WHERE {where} ORDER BY fit_score DESC, id",
        params,
    ).fetchall()

    print(f"Checking {len(rows)} job URLs ({args.workers} workers)...\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(check_url, r[0], r[1], r[2], r[3]): r
            for r in rows
        }
        done = 0
        for fut in as_completed(futures):
            result = fut.result()
            results.append(result)
            done += 1
            job_id, company, title, url, verdict, detail = result
            sym = {"open": "✓", "closed": "✗", "unknown": "?"}[verdict]
            print(f"[{done:3d}/{len(rows)}] {sym} id={job_id:3d} {verdict:7} {(company or '')[:25]:25} {detail}")

    # Sort: closed first, then unknown, then open
    order = {"closed": 0, "unknown": 1, "open": 2}
    results.sort(key=lambda r: (order[r[4]], r[0]))

    print(f"\n{'─'*70}")
    closed = [r for r in results if r[4] == "closed"]
    unknown = [r for r in results if r[4] == "unknown"]
    open_  = [r for r in results if r[4] == "open"]

    print(f"\nSUMMARY: {len(open_)} open  |  {len(closed)} closed  |  {len(unknown)} unknown\n")

    if closed:
        print(f"CLOSED ({len(closed)}):")
        for _, company, title, url, _, detail in closed:
            print(f"  {(company or '')[:30]:30} {title[:45]:45} [{detail}]")

    if unknown:
        print(f"\nUNKNOWN ({len(unknown)}) — could not determine:")
        for _, company, title, url, _, detail in unknown:
            print(f"  {(company or '')[:30]:30} {title[:45]:45} [{detail}]")

    if args.close and closed:
        ids = [r[0] for r in closed]
        conn.executemany(
            "UPDATE jobs SET status='closed' WHERE id=?",
            [(i,) for i in ids]
        )
        conn.commit()
        print(f"\nMarked {len(ids)} jobs as 'closed' in DB: {ids}")

    conn.close()


if __name__ == "__main__":
    main()
