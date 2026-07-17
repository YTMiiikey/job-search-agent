"""
Parse manually-saved job posting files and upsert them into jobs.db.

LinkedIn's job pages load content via JavaScript after page load, so
"Save Page As HTML" captures only an empty shell. Use .txt files instead:

  LinkedIn (recommended):
    1. Open the job page and wait for description to fully appear
    2. Ctrl+A → Ctrl+C to select and copy all text on the page
    3. Paste into a .txt file named after the job (e.g. "Pfizer_SrScientist.txt")
    4. Drop into data/saved_pages/

  Other job boards (Greenhouse, Lever, company sites):
    1. File → Save Page As → "Webpage, HTML Only"  (content is in static HTML)
    2. Drop the .html file into data/saved_pages/

  Then run:
    python scripts/parse_saved_pages.py

Processed files move to data/saved_pages/processed/.
"""

import json, re, sys
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

ROOT       = Path(__file__).resolve().parent.parent
INBOX      = ROOT / "data" / "saved_pages"
PROCESSED  = INBOX / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
import db
from config import classify_job


# ---------------------------------------------------------------------------
# Extractors — tried in order, first non-empty result wins
# ---------------------------------------------------------------------------

def extract_canonical_url(soup):
    tag = soup.find("link", rel="canonical") or soup.find("meta", property="og:url")
    if tag:
        return (tag.get("href") or tag.get("content") or "").strip()
    return ""


def extract_json_ld(soup):
    """Many job boards embed structured JobPosting data."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "JobPosting"), {})
            if data.get("@type") == "JobPosting":
                company = ""
                org = data.get("hiringOrganization", {})
                if isinstance(org, dict):
                    company = org.get("name", "")
                return {
                    "company":     company,
                    "title":       data.get("title", ""),
                    "location":    data.get("jobLocation", {}).get("address", {}).get("addressLocality", "")
                                   if isinstance(data.get("jobLocation"), dict) else "",
                    "description": BeautifulSoup(data.get("description", ""), "html.parser").get_text(" ", strip=True),
                }
        except Exception:
            pass
    return {}


def extract_linkedin(soup):
    def t(sel):
        el = soup.select_one(sel)
        return el.get_text(" ", strip=True) if el else ""

    company = (
        t(".job-details-jobs-unified-top-card__company-name")
        or t(".topcard__org-name-link")
        or t("[data-tracking-control-name='public_jobs_topcard-org-name']")
        or t(".jobs-unified-top-card__company-name")
    )
    title = (
        t("h1.job-details-jobs-unified-top-card__job-title")
        or t("h1.topcard__title")
        or t("h1.jobs-unified-top-card__job-title")
        or t("h1")
    )
    location = (
        t(".job-details-jobs-unified-top-card__primary-description-container")
        or t(".topcard__flavor--bullet")
        or t(".jobs-unified-top-card__subtitle-primary-grouping")
    )
    desc_el = (
        soup.select_one("#job-details")
        or soup.select_one(".jobs-description__content")
        or soup.select_one(".show-more-less-html__markup")
        or soup.select_one("[class*='description__text']")
    )
    description = desc_el.get_text("\n", strip=True) if desc_el else ""

    if title or company:
        return {"company": company, "title": title,
                "location": location, "description": description}
    return {}


def extract_generic(soup):
    """Fallback: grab og:title / og:description and visible body text."""
    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return (tag.get("content") or "").strip() if tag else ""

    title       = meta("og:title") or (soup.title.string.strip() if soup.title else "")
    description = meta("og:description")

    # Try to get a fuller description from the main content area
    for sel in ["main", "article", "#content", ".content", ".job-description",
                "[class*='description']", "[class*='job-detail']", "body"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text("\n", strip=True)
            if len(text) > len(description):
                description = text
            break

    return {"company": meta("og:site_name"), "title": title,
            "location": "", "description": description}


# ---------------------------------------------------------------------------

def extract_plain_text(path: Path):
    """
    Parse a .txt file containing text copied from a job page (Ctrl+A, Ctrl+C, paste).
    Tries to infer title/company from the filename and first lines of the file.
    The full text becomes the description so nothing is lost.
    """
    text = path.read_text(encoding="utf-8", errors="ignore").strip()

    # Infer title and company from filename: "Company_Title.txt" or "Title _ Company.txt"
    stem = path.stem
    company, title = "", ""
    # LinkedIn filename pattern: "Job Title _ Company _ LinkedIn"
    parts = [p.strip() for p in re.split(r"\s*[_|]\s*", stem)]
    parts = [p for p in parts if p.lower() not in ("linkedin", "indeed", "glassdoor")]
    if len(parts) >= 2:
        title   = parts[0]
        company = parts[1]
    elif parts:
        title = parts[0]

    # Try to extract URL from the text (LinkedIn, etc.)
    url_m = re.search(r'https?://[^\s]+/jobs/view/\d+', text)
    url = url_m.group(0).split("?")[0] if url_m else ""

    # Try to get a better title from the first non-boilerplate line
    first_lines = [l.strip() for l in text.splitlines() if l.strip()][:5]
    if first_lines and not title:
        title = first_lines[0]

    return url, {"company": company, "title": title, "location": "", "description": text}


def parse_html(path: Path):
    html = path.read_bytes()
    soup = BeautifulSoup(html, "html.parser")

    url = extract_canonical_url(soup)

    # Try extractors in priority order
    info = extract_json_ld(soup)
    if not info.get("title"):
        info = extract_linkedin(soup)
    if not info.get("title"):
        info = extract_generic(soup)

    return url, info


def parse_file(path: Path):
    if path.suffix.lower() in (".txt",):
        return extract_plain_text(path)
    return parse_html(path)


def process_file(html_path: Path):
    print(f"\nProcessing: {html_path.name}")
    url, info = parse_file(html_path)

    company     = (info.get("company") or "").strip()
    title       = (info.get("title")   or "").strip()
    location    = (info.get("location") or "").strip()
    description = (info.get("description") or "").strip()

    print(f"  title:    {title[:80]}")
    print(f"  company:  {company}")
    print(f"  location: {location}")
    print(f"  desc len: {len(description)} chars")
    print(f"  url:      {url[:80]}")

    if not title:
        print("  [!] Could not extract title — skipping")
        return

    db.init_db()
    conn = db.get_connection()

    # Try to match an existing row by URL
    existing = None
    if url:
        existing = conn.execute("SELECT id FROM jobs WHERE url=?", (url,)).fetchone()

    # Also try matching by title + company for LinkedIn /comm/ links vs /jobs/ links
    if not existing and title:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE title=? AND (company=? OR company IS NULL OR company='')",
            (title, company)
        ).fetchone()

    if existing:
        job_id = existing[0]
        conn.execute(
            "UPDATE jobs SET company=?, location=?, description=?, url=COALESCE(NULLIF(url,''),?) WHERE id=?",
            (company or None, location or None, description or None, url, job_id)
        )
        conn.commit()
        print(f"  Updated existing job id={job_id}")
    else:
        if not url:
            url = f"saved://{html_path.stem}"
        status, fit_rationale = classify_job(title, description, location)
        conn.execute(
            "INSERT OR IGNORE INTO jobs (source, company, title, location, url, description, date_found, status, fit_rationale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("saved_html", company, title, location, url, description, date.today().isoformat(), status, fit_rationale)
        )
        conn.commit()
        new_id = conn.execute("SELECT id FROM jobs WHERE url=?", (url,)).fetchone()
        print(f"  Inserted new job id={new_id[0] if new_id else '?'}")

    conn.close()

    # Move to processed/
    dest = PROCESSED / html_path.name
    html_path.rename(dest)
    print(f"  Moved to {dest.relative_to(ROOT)}")


def main():
    html_files = sorted(INBOX.glob("*.html")) + sorted(INBOX.glob("*.htm")) + sorted(INBOX.glob("*.txt"))
    if not html_files:
        print(f"No HTML files found in {INBOX.relative_to(ROOT)}/")
        print("Save a job posting page from your browser and drop it there.")
        return

    print(f"Found {len(html_files)} file(s) to process.")
    for f in html_files:
        try:
            process_file(f)
        except Exception as e:
            print(f"  [!] Error processing {f.name}: {e}")

    print("\nDone. Run scrape/score as usual to process new entries.")


if __name__ == "__main__":
    main()
