"""
Scrape LinkedIn job pages for jobs in jobs.db that are missing company/description.

First run: opens a real Chromium browser window so you can log into LinkedIn.
           Session is saved to credentials/linkedin_state.json for all future runs.

Subsequent runs: loads saved session and scrapes headlessly (no window needed).

Usage:
    python scripts/linkedin_scraper.py            # scrape all jobs missing description
    python scripts/linkedin_scraper.py --login    # force a fresh login
"""

import argparse, json, sys, time
from pathlib import Path

ROOT        = Path(__file__).resolve().parent.parent
STATE_FILE  = ROOT / "credentials" / "linkedin_state.json"

sys.path.insert(0, str(ROOT / "scripts"))
import db


def login_and_save():
    from playwright.sync_api import sync_playwright
    print("Opening browser — log into LinkedIn, then press Enter here to save session...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("https://www.linkedin.com/login")
        input("  [Press Enter after you have logged in] ")
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=str(STATE_FILE))
        browser.close()
    print(f"Session saved to {STATE_FILE}")


def scrape_job(page, job_id, url):
    """Navigate to a LinkedIn job page and return (company, title, location, description)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(2)

        def text(selector, default=""):
            el = page.query_selector(selector)
            return el.inner_text().strip() if el else default

        company  = text(".job-details-jobs-unified-top-card__company-name a") or \
                   text(".job-details-jobs-unified-top-card__company-name") or \
                   text("[class*='company-name']")
        title    = text("h1.job-details-jobs-unified-top-card__job-title") or \
                   text("h1[class*='job-title']")
        location = text(".job-details-jobs-unified-top-card__primary-description-container") or \
                   text("[class*='job-location']")
        desc_el  = page.query_selector("#job-details") or \
                   page.query_selector(".jobs-description__content") or \
                   page.query_selector("[class*='description']")
        desc = desc_el.inner_text().strip() if desc_el else ""

        # If we hit a login wall, the page won't have these elements
        if not company and not desc:
            print(f"  [!] id={job_id}: looks like a login wall — re-run with --login")
            return None
        return company, title, location, desc
    except Exception as e:
        print(f"  [!] id={job_id}: error scraping {url}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--login", action="store_true",
                        help="Force a fresh LinkedIn login and save session")
    args = parser.parse_args()

    if args.login or not STATE_FILE.exists():
        login_and_save()
        if args.login:
            return

    # Find jobs that are missing description or company
    db.init_db()
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT id, url, title FROM jobs WHERE source='linkedin_email' "
        "AND (description IS NULL OR description='' OR company IS NULL OR company='')"
    ).fetchall()
    conn.close()

    if not rows:
        print("No LinkedIn jobs missing details.")
        return

    print(f"Found {len(rows)} LinkedIn job(s) to fill in:")
    for r in rows:
        print(f"  id={r[0]}  {r[2][:60]}  {r[1]}")

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(STATE_FILE))
        page = ctx.new_page()

        for job_id, url, title in rows:
            print(f"\nScraping id={job_id}: {title[:50]}...")
            result = scrape_job(page, job_id, url)
            if not result:
                continue
            company, scraped_title, location, desc = result
            print(f"  company={company!r}  location={location!r}  desc_len={len(desc)}")

            conn = db.get_connection()
            conn.execute(
                "UPDATE jobs SET company=?, location=?, description=? WHERE id=?",
                (company or title, location, desc, job_id)
            )
            conn.commit()
            conn.close()
            print(f"  Updated id={job_id}")

        browser.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
