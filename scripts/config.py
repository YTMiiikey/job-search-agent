"""Shared configuration loading and job-classification filters.

All ingestion scripts (scrape_ats, scrape_open_tabs, parse_saved_pages,
import_linkedin_json, import_scraped_jobs) import from
here so that exclude_locations and exclude_keywords stay in one place.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

CONFIG_PATH  = Path(__file__).resolve().parent.parent / "data" / "companies.yaml"
PROFILE_PATH = Path(__file__).resolve().parent.parent / "user_profile.yaml"

_config_cache:  dict | None = None
_profile_cache: dict | None = None


def load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(CONFIG_PATH) as fh:
            _config_cache = yaml.safe_load(fh)
    return _config_cache


def load_profile() -> dict:
    """Load user_profile.yaml, raising a helpful error if it's missing."""
    global _profile_cache
    if _profile_cache is None:
        if not PROFILE_PATH.exists():
            raise FileNotFoundError(
                f"{PROFILE_PATH} not found.\n"
                "Copy user_profile.example.yaml → user_profile.yaml and fill in your details."
            )
        with open(PROFILE_PATH) as fh:
            _profile_cache = yaml.safe_load(fh)
    return _profile_cache


def matched_exclude_location(location: str,
                             exclude_locations: list[str]) -> str | None:
    loc = location.lower()
    for term in exclude_locations:
        if term.lower() in loc:
            return term
    return None


def matched_exclude_keyword(title: str, description: str,
                            exclude_keywords: list[str]) -> str | None:
    haystack = f"{title} {description}".lower()
    for kw in exclude_keywords:
        # Word-boundary match: a naive substring check on short keywords like
        # "itar" false-positives on "military", "sanitary", "voluntary", etc.
        if re.search(r"\b" + re.escape(kw.lower()) + r"\b", haystack):
            return kw
    return None


def classify_job(title: str, description: str, location: str,
                 config: dict | None = None) -> tuple[str, str | None]:
    """Return (status, fit_rationale) based on location and sponsorship filters.

    status is one of:
      'new'                — passes all filters; ready for scoring
      'exclude_location'   — location is outside target geography
      'exclude_sponsorship'— posting contains a no-visa-sponsorship signal
    """
    if config is None:
        config = load_config()
    loc_hit = matched_exclude_location(location, config.get("exclude_locations", []))
    if loc_hit:
        return ("exclude_location",
                f"Auto-excluded: location '{location}' matches '{loc_hit}'")
    kw_hit = matched_exclude_keyword(title, description,
                                     config.get("exclude_keywords", []))
    if kw_hit:
        return ("exclude_sponsorship",
                f"Auto-excluded: posting contains '{kw_hit}'")
    return "new", None
