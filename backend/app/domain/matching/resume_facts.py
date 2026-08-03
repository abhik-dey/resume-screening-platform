"""
Derive scorer inputs (years of experience, education text) from the
Resume Parsing Agent's structured output.

Pure and I/O-free. Kept separate from scorer.py because "what does this
resume say about experience?" and "how should experience be scored?" are
genuinely different questions — and this one has to cope with messy,
LLM-extracted date strings while the scorer works with clean numbers.
"""
import re
from datetime import datetime, timezone

# Matches a 4-digit year in the 1900s or 2000s. Deliberately conservative:
# a wrong year is worse than no year, since it silently corrupts the score.
_YEAR_PATTERN = re.compile(r"\b(19\d{2}|20\d{2})\b")

_PRESENT_MARKERS = ("present", "current", "now", "ongoing", "till date", "to date")


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = _YEAR_PATTERN.search(value)
    return int(match.group(1)) if match else None


def _is_present(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return any(marker in lowered for marker in _PRESENT_MARKERS)


def estimate_years_experience(parsed_data: dict | None, now_year: int | None = None) -> float | None:
    """Estimate total years of professional experience from parsed resume
    experience entries. Returns None if no usable dates are present —
    None means "unknown", which the scorer treats differently from 0.

    Overlapping roles are NOT double-counted: the total is computed from
    the union of covered years, so someone holding two concurrent positions
    from 2020-2022 gets 2 years, not 4.
    """
    if not parsed_data:
        return None
    entries = parsed_data.get("experience") or []
    if not entries:
        return None

    current_year = now_year or datetime.now(timezone.utc).year
    covered_years: set[int] = set()

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        start = _parse_year(entry.get("start_date"))
        if start is None:
            continue
        if _is_present(entry.get("end_date")) or not entry.get("end_date"):
            end = current_year
        else:
            end = _parse_year(entry.get("end_date")) or current_year

        if end < start:
            start, end = end, start
        # A role spanning 2020-2022 covers 2020 and 2021 as full years;
        # counting the end year too would inflate every entry by one.
        covered_years.update(range(start, max(end, start + 1)))

    if not covered_years:
        return None
    return float(len(covered_years))


def extract_education_text(parsed_data: dict | None) -> str | None:
    """Flatten parsed education entries into a single string the scorer's
    keyword-based level detection can inspect."""
    if not parsed_data:
        return None
    entries = parsed_data.get("education") or []
    if not entries:
        return None

    parts: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        for key in ("degree", "field_of_study", "institution"):
            value = entry.get(key)
            if value:
                parts.append(str(value))
    return " ".join(parts) if parts else None
