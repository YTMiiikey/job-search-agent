#!/usr/bin/env python3
"""Validate generated resume/cover-letter content for disallowed terms.

Catches fabricated skills, wrong tool names, or inaccurate characterization
language before files are written or submitted.

Usage:
    # Scan all application folders for violations
    python3 scripts/validate.py

    # Validate a specific folder
    python3 scripts/validate.py applications/8_Adimab_ScientistComputationalProteinDesign

    # Validate a string in Python
    from validate import validate_text, DISALLOWED
    errors = validate_text(my_text)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ── Disallowed patterns ────────────────────────────────────────────────────
# Loaded from user_profile.yaml at first use. Each entry in the YAML is:
#   { pattern: "<python regex>", message: "<human-readable explanation>" }
# Patterns are compiled with re.IGNORECASE | re.DOTALL.
#
# Define your own patterns to catch fabricated skills, wrong tool names,
# or cross-contaminated facts between resume sections.

def _load_disallowed() -> list[tuple[re.Pattern, str]]:
    try:
        from config import load_profile
        patterns = load_profile().get("disallowed_patterns") or []
        return [
            (re.compile(entry["pattern"], re.IGNORECASE | re.DOTALL), entry["message"])
            for entry in patterns
        ]
    except Exception:
        return []

_COMPILED = _load_disallowed()


def validate_text(text: str) -> list[dict]:
    """Return list of {pattern, message, context} dicts for every violation found."""
    errors = []
    for pattern, message in _COMPILED:
        for m in pattern.finditer(text):
            start = max(0, m.start() - 60)
            end   = min(len(text), m.end() + 60)
            ctx   = text[start:end].replace("\n", " ").strip()
            errors.append({
                "pattern": pattern.pattern,
                "message": message,
                "match":   m.group(0),
                "context": f"...{ctx}...",
            })
    return errors


def validate_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    errors = validate_text(text)
    for e in errors:
        e["file"] = str(path)
    return errors


def validate_folder(folder: Path) -> list[dict]:
    errors = []
    for fname in ("resume.md", "cover_letter.md"):
        f = folder / fname
        if f.exists():
            errors.extend(validate_file(f))
    return errors


def validate_and_raise(text: str, context: str = "content") -> None:
    """Call from draft scripts: raises ValueError listing all violations."""
    errors = validate_text(text)
    if errors:
        lines = [f"\n[VALIDATION ERROR] {len(errors)} violation(s) in {context}:"]
        for i, e in enumerate(errors, 1):
            lines.append(f"  {i}. {e['message']}")
            lines.append(f"     Match: {repr(e['match'])}")
            lines.append(f"     Context: {e['context']}")
        raise ValueError("\n".join(lines))


def main():
    apps_dir = ROOT / "applications"

    # Optionally restrict to a single folder passed as argument
    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted(p for p in apps_dir.iterdir() if p.is_dir()
                         and not p.name.startswith("0.")   # skip submitted
                         and p.name != "Archive")

    all_errors = []
    for folder in targets:
        errs = validate_folder(folder)
        all_errors.extend(errs)
        if errs:
            print(f"\n{'─'*60}")
            print(f"VIOLATIONS in {folder.name}:")
            for e in errs:
                print(f"  [{e['file'].split('/')[-1]}] {e['message']}")
                print(f"    match:   {repr(e['match'])}")
                print(f"    context: {e['context']}")

    print(f"\n{'─'*60}")
    if all_errors:
        print(f"TOTAL: {len(all_errors)} violation(s) across {len(targets)} folder(s) checked.")
        sys.exit(1)
    else:
        print(f"OK — 0 violations across {len(targets)} folder(s) checked.")


if __name__ == "__main__":
    main()
