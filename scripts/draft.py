#!/usr/bin/env python3
"""Unified draft pipeline: generate tailored resume + cover letter for one job.

Usage:
    python3 scripts/draft.py <job_id> [<job_id> ...]
    python3 scripts/draft.py 280
    python3 scripts/draft.py 280 281 282

Pulls job from DB, calls Claude to generate tailored content, validates it,
writes resume.md / cover_letter.md / job_info.txt, builds DOCX + PDF, and
marks the job as 'drafted' in the DB.

Cover letter is generated only for jobs with fit_score >= 6.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import db
from config import load_profile
from draft_all import (
    SKILLS_COMP_REF, SKILLS_EXP_REF,
    ELEVATE_AI_ML_COMP, ELEVATE_AI_ML, ELEVATE_WET_LAB, ELEVATE_VHH_LNP,
    DUKE_EXPERIENCE, EDUCATION, PUBLICATIONS, PATENTS, CONFERENCES, LEADERSHIP,
    ELEVATE_HEADER, build_resume, write_job_info,
)
from docx_builder import (
    build_resume_docx_from_md, build_cover_letter_docx,
    TEMPLATE_COMP, TEMPLATE_EXP,
)
from validate import validate_and_raise

APPS_DIR = ROOT / "applications"

# ── Stop words for slug generation ────────────────────────────────────────────

_SLUG_STOP = {
    "a", "an", "the", "and", "or", "of", "for", "in", "at", "to", "with",
    "by", "as", "on", "is", "are", "its", "be", "this",
    "i", "ii", "iii",
}

# ── Profile text for LLM prompts (loaded from user_profile.yaml) ───────────────

def _build_prompts():
    p = load_profile()
    name     = p.get("name", "Candidate")
    email    = p.get("email", "")
    phone    = p.get("phone", "")
    location = p.get("location", "")
    profile  = p.get("draft_profile", p.get("scoring_profile", ""))

    system_prompt = textwrap.dedent(f"""\
        You are a professional resume writer generating tailored job application materials
        for {name}. You MUST follow all accuracy rules in the candidate profile exactly.
        Respond ONLY with valid JSON — no markdown fences, no explanation.
    """).strip()

    contact_block = name
    if location:
        contact_block += f"\n{location}"
    if email and phone:
        contact_block += f"\n{email} | {phone}"
    elif email:
        contact_block += f"\n{email}"

    user_template = textwrap.dedent(f"""\
        Candidate profile:
        {{profile}}

        Job description:
        Company: {{company}}
        Title: {{title}}
        Location: {{location}}
        Score: {{score}}/9

        Description (first 4000 chars):
        {{description}}

        Generate JSON with these keys:

        "template": "comp" if the role emphasizes computational/ML skills first,
                    "exp" if it emphasizes wet-lab / experimental skills first.

        "sections": ordered list of section keys to include in the Experience section.
                    The available keys are defined in draft_all.py — check that file
                    for the full list and choose the most relevant subset ordered by
                    relevance to this specific JD.

        "summary": list of exactly 4 strings. Each is one resume summary bullet (no leading "- ").
                   Bullets must be tailored to this specific JD — mention the company by name in
                   at least one bullet. First bullet: strongest match skill + quantified outcome.
                   Last bullet: PhD/degree credentials, publications, location/relocation.
                   Each bullet: 1-3 sentences, 30-60 words.

        "cover_letter": full cover letter text if score >= 6, else null.
                        Format: header block, blank line, salutation, blank line,
                        3-4 body paragraphs (~80-120 words each), blank line, closing.
                        Header:
                        {contact_block}
                        Salutation: "Dear [Company] Hiring Team,"
                        Open with what specifically excites you about this company/role.
                        Para 2: most relevant 2-3 skills with specific quantified examples.
                        Para 3: one acknowledged gap and why transferable skills still fit.
                        Para 4 (optional): closing enthusiasm + relocation if needed.
                        Closing: "Sincerely,\\n{name}"

        Respond with JSON only.
    """).strip()

    return profile, system_prompt, user_template


PROFILE_SUMMARY, SYSTEM_PROMPT, USER_TEMPLATE = _build_prompts()


def make_slug(text: str, max_words: int = 5) -> str:
    """Convert a string to CamelCase slug, filtering stop words.

    Preserves all-uppercase words (acronyms like AI, ML, VHH) as-is.
    """
    words = re.findall(r"[A-Za-z0-9]+", text)
    kept = []
    for w in words:
        if w.lower() in _SLUG_STOP:
            continue
        # Preserve all-caps acronyms (2-5 letters); capitalize everything else
        kept.append(w if (w.isupper() and 2 <= len(w) <= 5) else w.capitalize())
    return "".join(kept[:max_words])


def make_folder_name(score: int, company: str, title: str) -> str:
    company_slug = make_slug(company, max_words=3)
    role_slug = make_slug(title, max_words=5)
    return f"{score}_{company_slug}_{role_slug}"


def pandoc(src: Path, dst: Path, extra_args: list[str] = ()) -> bool:
    cmd = ["pandoc", str(src)] + list(extra_args) + ["-o", str(dst)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  pandoc error: {result.stderr[:200]}")
    return result.returncode == 0


def generate_draft(client, job: dict) -> dict:
    """Call Claude to generate tailored draft content. Returns parsed dict."""
    desc = (job.get("description") or "")[:4000]
    user_msg = USER_TEMPLATE.format(
        profile=PROFILE_SUMMARY,
        company=job.get("company", ""),
        title=job.get("title", ""),
        location=job.get("location", ""),
        score=job.get("fit_score", 0) or 0,
        description=desc,
    )
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = response.content[0].text.strip()
    # Strip any accidental markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def draft_job(client, job: dict) -> Path:
    """Generate, validate, and write all application files for one job. Returns folder path."""
    jid = job["id"]
    company = job.get("company", "Unknown")
    title = job.get("title", "Role")
    score = job.get("fit_score") or 0
    has_cl = score >= 6

    print(f"\n{'─'*60}")
    print(f"[{jid}] {company} — {title}  (score {score}/9)")
    print("  Generating draft via Claude API...")

    result = generate_draft(client, job)

    template_key = result.get("template", "comp")
    sections = result.get("sections", ["ai_ml_comp", "wet_lab"])
    summary_bullets = result.get("summary", [])
    cover_letter_text = result.get("cover_letter") if has_cl else None

    template = TEMPLATE_COMP if template_key == "comp" else TEMPLATE_EXP
    skills = SKILLS_COMP_REF if template_key == "comp" else SKILLS_EXP_REF

    folder_name = make_folder_name(score, company, title)
    folder = APPS_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    # Build and validate resume
    resume_md = build_resume(summary_bullets, skills, sections)
    validate_and_raise(resume_md, f"resume for {folder_name}")
    (folder / "resume.md").write_text(resume_md, encoding="utf-8")

    # Build and validate cover letter
    if cover_letter_text:
        validate_and_raise(cover_letter_text, f"cover letter for {folder_name}")
        (folder / "cover_letter.md").write_text(cover_letter_text, encoding="utf-8")

    # Write job reference info
    write_job_info(db.get_connection(), jid, folder)

    # Build DOCX
    build_resume_docx_from_md(resume_md, folder / "resume.docx", template_path=template)
    if cover_letter_text:
        build_cover_letter_docx(cover_letter_text, folder / "cover_letter.docx")

    # Build PDF + TXT via pandoc
    pandoc(folder / "resume.md", folder / "resume.pdf",
           ["--pdf-engine=xelatex", "-V", "geometry:margin=0.75in",
            "-V", "fontsize=10pt", "-V", "colorlinks=true"])
    pandoc(folder / "resume.md", folder / "resume.txt", ["-t", "plain"])
    if cover_letter_text:
        pandoc(folder / "cover_letter.md", folder / "cover_letter.pdf",
               ["--pdf-engine=xelatex", "-V", "geometry:margin=1in",
                "-V", "fontsize=11pt", "-V", "colorlinks=true"])
        pandoc(folder / "cover_letter.md", folder / "cover_letter.txt", ["-t", "plain"])

    # Mark as drafted in DB
    conn = db.get_connection()
    conn.execute("UPDATE jobs SET status='drafted' WHERE id=?", (jid,))
    conn.commit()
    conn.close()

    print(f"  → {folder_name}")
    print(f"     Template: {template_key}, Sections: {sections}")
    print(f"     Cover letter: {'yes' if cover_letter_text else 'no (score < 6)'}")

    return folder


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft application materials for a job")
    parser.add_argument("job_ids", nargs="+", type=int, help="One or more job IDs from the DB")
    parser.add_argument("--force", action="store_true",
                        help="Re-draft even if the job is already drafted (overwrites existing files)")
    args = parser.parse_args()

    jobs_by_id = {j["id"]: j for j in db.get_jobs()}

    missing = [jid for jid in args.job_ids if jid not in jobs_by_id]
    if missing:
        print(f"Error: job IDs not found: {missing}", file=sys.stderr)
        sys.exit(1)

    # Warn about already-drafted jobs unless --force
    already_drafted = [jid for jid in args.job_ids
                       if jobs_by_id[jid].get("status") == "drafted"]
    if already_drafted and not args.force:
        for jid in already_drafted:
            j = jobs_by_id[jid]
            print(f"  SKIP [{jid}] {j['company']} — {j['title']} (already drafted; use --force to overwrite)")
        remaining = [jid for jid in args.job_ids if jid not in already_drafted]
        if not remaining:
            sys.exit(0)
        args.job_ids = remaining

    import anthropic
    client = anthropic.Anthropic()

    for jid in args.job_ids:
        job = jobs_by_id[jid]
        try:
            draft_job(client, job)
        except Exception as e:
            print(f"  ERROR drafting job {jid}: {e}", file=sys.stderr)
            raise

    print(f"\nDone. {len(args.job_ids)} job(s) drafted.")


if __name__ == "__main__":
    main()
