#!/usr/bin/env python3
"""Check whether the one-time setup is complete.

Run this before using the pipeline for the first time, or to diagnose
why a command isn't working.

Usage:
    python3 scripts/check_setup.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHECKS = []


def check(label: str, ok: bool, fix: str = "") -> bool:
    CHECKS.append((label, ok, fix))
    return ok


def run():
    # ── Required files ────────────────────────────────────────────────────
    check(
        "user_profile.yaml exists",
        (ROOT / "user_profile.yaml").exists(),
        "cp user_profile.example.yaml user_profile.yaml  # then fill in your details",
    )

    check(
        "scripts/draft_all.py exists",
        (ROOT / "scripts" / "draft_all.py").exists(),
        "cp draft_all.example.py scripts/draft_all.py  # then customize with your resume content",
    )

    check(
        "reference_resume_comp.docx exists",
        (ROOT / "reference_resume_comp.docx").exists(),
        "Add your resume DOCX as reference_resume_comp.docx in the project root",
    )

    check(
        "referece_resume_exp.docx exists",
        (ROOT / "referece_resume_exp.docx").exists(),
        "Add your resume DOCX as referece_resume_exp.docx in the project root  (note the typo — intentional)",
    )

    check(
        "data/jobs.db exists",
        (ROOT / "data" / "jobs.db").exists(),
        "python3 scripts/db.py",
    )

    # ── Python packages ───────────────────────────────────────────────────
    for pkg in ("anthropic", "yaml", "docx", "requests", "thefuzz"):
        import_name = {"yaml": "yaml", "docx": "docx", "thefuzz": "thefuzz"}.get(pkg, pkg)
        try:
            __import__(import_name)
            ok = True
        except ImportError:
            ok = False
        check(
            f"Python package '{pkg}' installed",
            ok,
            "pip install -r requirements.txt",
        )

    # ── External tools ────────────────────────────────────────────────────
    check(
        "pandoc installed",
        shutil.which("pandoc") is not None,
        "sudo apt install pandoc  (Linux/WSL)  |  brew install pandoc  (Mac)",
    )

    # ── API key ───────────────────────────────────────────────────────────
    import os
    check(
        "ANTHROPIC_API_KEY set",
        bool(os.environ.get("ANTHROPIC_API_KEY")),
        "export ANTHROPIC_API_KEY=sk-ant-...  (add to ~/.bashrc to persist)",
    )

    # ── user_profile.yaml fields ──────────────────────────────────────────
    if (ROOT / "user_profile.yaml").exists():
        try:
            import yaml
            with open(ROOT / "user_profile.yaml") as fh:
                profile = yaml.safe_load(fh) or {}
            for field in ("name", "email", "scoring_profile", "draft_profile"):
                val = profile.get(field, "")
                filled = bool(val and str(val).strip() and "example.com" not in str(val)
                              and "Jane Smith" not in str(val))
                check(
                    f"user_profile.yaml: '{field}' filled in",
                    filled,
                    f"Open user_profile.yaml and fill in the '{field}' field",
                )
        except Exception as e:
            check("user_profile.yaml: valid YAML", False, f"Fix YAML syntax error: {e}")

    # ── Print results ─────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total  = len(CHECKS)
    width  = max(len(label) for label, _, _ in CHECKS)

    print(f"\nSetup check — {passed}/{total} passed\n")
    for label, ok, fix in CHECKS:
        icon = "✓" if ok else "✗"
        print(f"  {icon}  {label:{width}}")
        if not ok and fix:
            print(f"       → {fix}")

    print()
    if passed == total:
        print("All checks passed. You're ready to run the pipeline.")
        print("Start with: python3 scripts/scrape_ats.py")
    else:
        print(f"{total - passed} item(s) need attention. Fix the issues above, then re-run this script.")

    return passed == total


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
