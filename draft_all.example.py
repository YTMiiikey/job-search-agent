#!/usr/bin/env python3
"""Resume section definitions — copy this file to draft_all.py and customize.

draft.py imports constants and build_resume() from this file. Each section key
you define here becomes available to the LLM when deciding how to assemble a
tailored resume for a specific job description.

SETUP:
  1. Copy this file:  cp draft_all.example.py scripts/draft_all.py
  2. Replace all placeholder content with your own resume text.
  3. Add or remove sections to match your background.
  4. Provide one or two reference DOCX templates in the project root:
       reference_resume_comp.docx  (primary template — used when template = "comp")
       referece_resume_exp.docx    (alternate template — used when template = "exp", optional)
     What the two variants represent is up to you: different skill orderings, industry vs.
     academic framing, or anything else. If you only have one resume, copy it with both names.
     These files control formatting only; content is rebuilt from the sections below each time.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import db
from validate import validate_and_raise

APPS_DIR = ROOT / "applications"

# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# Appears at the top of every resume.
# ──────────────────────────────────────────────────────────────────────────────

HEADER = """\
**Your Name**

> City, State ZIP • your.email@example.com • +1 555-000-0000 •
> [LinkedIn](https://linkedin.com/in/your-profile) |
> [GitHub](https://github.com/your-handle)"""

# ──────────────────────────────────────────────────────────────────────────────
# TECHNICAL SKILLS
# Two variants: computational-first (comp) and experimental-first (exp).
# Choose the appropriate one per job using draft.py's template selection.
# ──────────────────────────────────────────────────────────────────────────────

SKILLS_COMP_REF = """\
# TECHNICAL SKILLS

- **Computational / technical:** [list your computational, software, and analytical skills]
- **Experimental / wet-lab:** [list your lab or hands-on technical skills]"""

SKILLS_EXP_REF = """\
# TECHNICAL SKILLS

- **Experimental / wet-lab:** [list your lab or hands-on technical skills]
- **Computational / technical:** [list your computational, software, and analytical skills]"""

# ──────────────────────────────────────────────────────────────────────────────
# EXPERIENCE SECTIONS
# Define one constant per logical group of bullets.
# Name them descriptively — draft.py's LLM prompt lists the available keys
# so the model can choose the most relevant subset for each JD.
#
# Section key naming convention (used as dict keys in build_resume below):
#   "comp"        — computational/technical project
#   "exp"         — experimental/hands-on project
#   "delivery"    — delivery, formulation, or translation work
#   "leadership"  — team lead / cross-functional work
#
# You can define as many sections as you like.
# ──────────────────────────────────────────────────────────────────────────────

# Replace the header line format below with your actual employer and role.
_ROLE_PAD = " " * 80  # adjust so the date aligns to the right margin in your DOCX template

COMPANY_HEADER = f"""\
> **Company Name (and any DBA)**
>
> **Your Job Title{_ROLE_PAD}** Start – End"""

# ── Section 1: computational/ML work ─────────────────────────────────────────
SECTION_COMP = """\
***Descriptive Sub-heading for Your Computational Work***

- [Bullet 1: outcome/impact statement — what did you build and what did it enable?]
- [Bullet 2: technical approach — which tools/models/methods did you use?]
- [Bullet 3: scale or scope — datasets, throughput, team, cost savings, etc.]
- [Bullet 4 (optional): cross-functional or leadership aspect of the work]"""

# ── Section 2: experimental/wet-lab work ─────────────────────────────────────
SECTION_EXP = """\
***Descriptive Sub-heading for Your Experimental Work***

- [Bullet 1: quantified outcome — hit rates, throughput, milestones, publications]
- [Bullet 2: methods — which assays, instruments, or protocols did you develop/use?]
- [Bullet 3: data or downstream impact of the experimental work]"""

# ── Section 3: optional specialization (e.g., delivery, imaging, genomics) ───
SECTION_SPECIALTY = """\
***Descriptive Sub-heading for a Specialized Sub-project***

- [Single or multi-bullet description of a specialized project relevant to certain JDs]"""

# ──────────────────────────────────────────────────────────────────────────────
# EARLIER EXPERIENCE / GRADUATE WORK
# ──────────────────────────────────────────────────────────────────────────────

PRIOR_EXPERIENCE = """\
> **Prior Employer or University**
>
> **Your Role or Graduate Title,** *Lab / Advisor info if academic*  Start – End

- [Dissertation / main project summary]
- [Key methods or results]
- [Publications, patents, or downstream impact]"""

# ──────────────────────────────────────────────────────────────────────────────
# EDUCATION
# ──────────────────────────────────────────────────────────────────────────────

EDUCATION = """\
# EDUCATION

> **Ph.D. in [Field] @ [University]**                                        [Years]
>
> **B.S. in [Field] @ [University]**                                         [Years]"""

# ──────────────────────────────────────────────────────────────────────────────
# PUBLICATIONS, PATENTS, CONFERENCES, LEADERSHIP (add only if applicable)
# ──────────────────────────────────────────────────────────────────────────────

PUBLICATIONS = """\
# PUBLICATIONS

- Author, A., **Your, N.**, & Collaborator, C. (Year). Title. *Journal*, vol(issue), pages."""

PATENTS = """\
# PATENTS

- "Patent title", PCT/US00/000000"""

CONFERENCES = """\
# CONFERENCES & PRESENTATIONS

**Conference Name** Month Year

Brief description of your poster or talk."""

LEADERSHIP = """\
# LEADERSHIP & ACTIVITIES

> **Role, Organization,** Institution  Start – End

- One or two bullets about impact or scope."""

# ──────────────────────────────────────────────────────────────────────────────
# SECTION KEY → CONSTANT MAPPING
# Maps the string keys the LLM uses in "sections" to the constants above.
# Customize this to match the sections you defined.
# ──────────────────────────────────────────────────────────────────────────────

SECTION_MAP: dict[str, str] = {
    "comp":      SECTION_COMP,
    "exp":       SECTION_EXP,
    "specialty": SECTION_SPECIALTY,
}

# ──────────────────────────────────────────────────────────────────────────────
# build_resume() — called by draft.py
#
# Assembles the full resume markdown from:
#   summary_bullets — list of strings from the LLM (tailored to the JD)
#   skills_block    — SKILLS_COMP_REF or SKILLS_EXP_REF
#   section_keys    — ordered list of section keys chosen by the LLM
# ──────────────────────────────────────────────────────────────────────────────

def build_resume(summary_bullets: list[str], skills_block: str,
                 section_keys: list[str]) -> str:
    parts = [HEADER, ""]

    # Summary
    parts.append("# SUMMARY\n")
    for b in summary_bullets:
        parts.append(f"- {b}")
    parts.append("")

    # Skills
    parts.append(skills_block)
    parts.append("")

    # Professional experience header
    parts.append("# PROFESSIONAL EXPERIENCE\n")
    parts.append(COMPANY_HEADER)
    parts.append("")

    # Experience sections chosen by the LLM
    for key in section_keys:
        section = SECTION_MAP.get(key)
        if section:
            parts.append(section)
            parts.append("")

    # Earlier / prior experience
    parts.append(PRIOR_EXPERIENCE)
    parts.append("")

    # Education + optional extras
    parts.append(EDUCATION)
    # Uncomment lines below if you have publications, patents, etc.:
    # parts.extend(["", PUBLICATIONS])
    # parts.extend(["", PATENTS])
    # parts.extend(["", CONFERENCES])
    # parts.extend(["", LEADERSHIP])

    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# write_job_info() — called by draft.py
# Writes a plain-text summary of the job alongside the application files.
# ──────────────────────────────────────────────────────────────────────────────

def write_job_info(conn, job_id: int, folder: Path) -> None:
    row = conn.execute(
        "SELECT company, title, location, url, fit_score, fit_rationale, description "
        "FROM jobs WHERE id=?", (job_id,)
    ).fetchone()
    if not row:
        return
    company, title, location, url, score, rationale, description = row
    lines = [
        f"Company:   {company}",
        f"Title:     {title}",
        f"Location:  {location}",
        f"URL:       {url}",
        f"Score:     {score}/9",
        f"Rationale: {rationale}",
        "",
        "─" * 60,
        "",
        description or "",
    ]
    (folder / "job_info.txt").write_text("\n".join(lines), encoding="utf-8")
