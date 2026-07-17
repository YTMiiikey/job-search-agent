"""Scrape job postings from company ATS (Greenhouse/Lever/Ashby) public APIs,
filter by keyword, and store new postings in data/jobs.db.

Usage:
    python scripts/scrape_ats.py
"""

import re
import html
from datetime import date, timezone, datetime
from pathlib import Path

import requests

import db
from config import (
    load_config, classify_job,
    matched_exclude_location, matched_exclude_keyword,
)


def strip_html(raw_html):
    if not raw_html:
        return ""
    text = html.unescape(raw_html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def matches_keywords(title, description, keywords):
    haystack = f"{title} {description}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def matches_title_keywords(title, title_keywords):
    """Require at least one title_keyword to appear in the job title."""
    if not title_keywords:
        return True
    t = title.lower()
    return any(kw.lower() in t for kw in title_keywords)


def fetch_greenhouse(board_token):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        postings.append({
            "title": job.get("title", ""),
            "location": (job.get("location") or {}).get("name", ""),
            "url": job.get("absolute_url", ""),
            "description": strip_html(job.get("content", "")),
        })
    return postings


def fetch_lever(board_token):
    url = f"https://api.lever.co/v0/postings/{board_token}?mode=json"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json():
        postings.append({
            "title": job.get("text", ""),
            "location": (job.get("categories") or {}).get("location", ""),
            "url": job.get("hostedUrl", ""),
            "description": strip_html(job.get("descriptionPlain", "") or job.get("description", "")),
        })
    return postings


def fetch_ashby(board_token):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_token}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    postings = []
    for job in resp.json().get("jobs", []):
        postings.append({
            "title": job.get("title", ""),
            "location": job.get("location", ""),
            "url": job.get("jobUrl", ""),
            "description": strip_html(job.get("descriptionPlain", "") or job.get("description", "")),
        })
    return postings


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


def main():
    config = load_config()
    keywords = config.get("keywords", [])
    title_keywords = config.get("title_keywords", [])
    today = date.today().isoformat()

    db.init_db()

    total_new = 0
    total_excluded = 0
    total_excluded_loc = 0
    for company in config.get("companies", []):
        ats = company.get("ats")
        fetcher = FETCHERS.get(ats)
        if not fetcher:
            continue  # 'manual' or unsupported ATS

        name = company["name"]
        try:
            postings = fetcher(company["board_token"])
        except requests.RequestException as e:
            print(f"[{name}] fetch failed: {e}")
            continue

        company_no_sponsorship = company.get("no_sponsorship", False)

        matched = 0
        new_count = 0
        excluded_count = 0
        excluded_loc_count = 0
        for posting in postings:
            if not matches_keywords(posting["title"], posting["description"], keywords):
                continue
            if not matches_title_keywords(posting["title"], title_keywords):
                continue
            matched += 1

            if company_no_sponsorship:
                status = "exclude_sponsorship"
                fit_rationale = f"Auto-excluded: {name} does not sponsor work visas (company-level flag)"
            else:
                status, fit_rationale = classify_job(
                    posting["title"], posting["description"], posting["location"], config
                )

            inserted = db.upsert_job(
                source=ats,
                company=name,
                title=posting["title"],
                location=posting["location"],
                url=posting["url"],
                description=posting["description"],
                date_found=today,
                status=status,
                fit_rationale=fit_rationale,
            )
            if inserted:
                total_new += 1
                if status == "exclude_location":
                    excluded_loc_count += 1
                    total_excluded_loc += 1
                elif status == "exclude_sponsorship":
                    excluded_count += 1
                    total_excluded += 1
                else:
                    new_count += 1

        print(f"[{name}] {len(postings)} postings, {matched} matched keywords, "
              f"{new_count} new, {excluded_count} excl-sponsorship, "
              f"{excluded_loc_count} excl-location")

    actionable = total_new - total_excluded - total_excluded_loc
    print(f"\nDone. {actionable} new job(s) added, "
          f"{total_excluded} excluded (sponsorship/clearance), "
          f"{total_excluded_loc} excluded (non-US location).")


if __name__ == "__main__":
    main()
