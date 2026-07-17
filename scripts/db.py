"""SQLite helpers for the job search pipeline."""

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    company TEXT,
    title TEXT NOT NULL,
    location TEXT,
    url TEXT NOT NULL UNIQUE,
    description TEXT,
    date_found TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    fit_score INTEGER,
    fit_rationale TEXT
);

CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    submitted_at TEXT NOT NULL DEFAULT (date('now')),
    platform TEXT,
    notes TEXT,
    followup_due TEXT,
    outcome TEXT
);
"""


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _normalize_title(title: str) -> str:
    """Lowercase, strip seniority/level noise, collapse whitespace for fuzzy matching."""
    t = title.lower()
    # Remove common seniority prefixes that differ across sources
    t = re.sub(r"\b(senior|sr\.?|junior|jr\.?|principal|staff|lead|associate|"
               r"i+v?|vii?|viii?|ix|[ivx]+)\b", " ", t)
    # Remove punctuation and collapse whitespace
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _is_duplicate(conn, company: str, title: str) -> bool:
    """Return True if a job with the same company and a near-identical title exists."""
    if not company or not title:
        return False
    norm_new = _normalize_title(title)
    rows = conn.execute(
        "SELECT title FROM jobs WHERE lower(company) = lower(?)", (company,)
    ).fetchall()
    for (existing_title,) in rows:
        norm_existing = _normalize_title(existing_title)
        # Treat as duplicate if normalized titles share ≥ 80% of words
        words_new = set(norm_new.split())
        words_existing = set(norm_existing.split())
        if not words_new or not words_existing:
            continue
        overlap = len(words_new & words_existing) / max(len(words_new), len(words_existing))
        if overlap >= 0.7:
            return True
    return False


def upsert_job(source, company, title, location, url, description, date_found,
                status="new", fit_rationale=None):
    """Insert a job if its URL isn't already present and no fuzzy duplicate exists.

    Returns True if inserted, False if skipped (URL duplicate or fuzzy title match).
    """
    conn = get_connection()
    try:
        # Fast path: exact URL dedup
        existing = conn.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
        if existing:
            return False
        # Fuzzy dedup: same company + near-identical title from a different source
        if _is_duplicate(conn, company, title):
            return False
        conn.execute(
            """INSERT INTO jobs (source, company, title, location, url, description, date_found, status, fit_rationale)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, company, title, location, url, description, date_found, status, fit_rationale),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_jobs(status=None):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    if status:
        rows = conn.execute("SELECT * FROM jobs WHERE status = ?", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM jobs").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_status(job_id, status, fit_score=None, fit_rationale=None):
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status = ?, fit_score = COALESCE(?, fit_score), "
        "fit_rationale = COALESCE(?, fit_rationale) WHERE id = ?",
        (status, fit_score, fit_rationale, job_id),
    )
    conn.commit()
    conn.close()


def record_submission(job_id, platform=None, notes=None, followup_days=14):
    """Mark a job as submitted and create a submissions row.

    followup_days: days until a follow-up reminder is due (default 14).
    Returns the new submission id.
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    followup_due = (date.today() + timedelta(days=followup_days)).isoformat()
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO submissions (job_id, submitted_at, platform, notes, followup_due)
           VALUES (?, ?, ?, ?, ?)""",
        (job_id, today, platform, notes, followup_due),
    )
    submission_id = cur.lastrowid
    conn.execute("UPDATE jobs SET status='submitted' WHERE id=?", (job_id,))
    conn.commit()
    conn.close()
    return submission_id


def get_submissions(outcome=None):
    """Return all submission rows, optionally filtered by outcome."""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    if outcome is not None:
        rows = conn.execute(
            "SELECT s.*, j.company, j.title FROM submissions s "
            "JOIN jobs j ON s.job_id = j.id WHERE s.outcome = ?", (outcome,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT s.*, j.company, j.title FROM submissions s "
            "JOIN jobs j ON s.job_id = j.id ORDER BY s.submitted_at DESC"
        ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_followups_due(as_of=None):
    """Return submissions where followup_due <= as_of and outcome is still NULL."""
    from datetime import date
    cutoff = as_of or date.today().isoformat()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT s.*, j.company, j.title, j.url FROM submissions s "
        "JOIN jobs j ON s.job_id = j.id "
        "WHERE s.followup_due <= ? AND s.outcome IS NULL "
        "ORDER BY s.followup_due",
        (cutoff,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    init_db()
    print(f"Initialized database at {DB_PATH}")
