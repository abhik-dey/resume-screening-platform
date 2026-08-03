"""
Skill normalization — the dictionary-lookup fast path.

Pure and I/O-free, same spirit as domain/validation/resume_file.py: given
a raw skill string, either resolve it deterministically via the curated
dictionary, or report it as unresolved so the caller can fall back to an
LLM. Fully unit-testable without a database, filesystem, or LLM call.
"""
import re
from dataclasses import dataclass

from app.domain.entities.skill import SkillCategory
from app.domain.skills.dictionary import SKILL_LOOKUP

# Dictionary-resolved skills are exact, reproducible matches -- full
# confidence. LLM-resolved skills (see the agent) get a lower fixed
# confidence instead of relying on the LLM to self-report one, since
# LLM self-reported confidence scores are notoriously poorly calibrated.
DICTIONARY_CONFIDENCE = 1.0


@dataclass
class ResolvedSkill:
    raw: str
    canonical_name: str
    category: SkillCategory
    confidence: float


def _normalize_key(raw: str) -> str:
    """Lowercase, collapse whitespace, and strip periods so that "C++",
    "c++", "C  ++" etc. reduce to a comparable key before lookup.
    Word-based variants (e.g. "C Plus Plus") are handled by the dictionary
    itself having that exact phrase as a separate alias, not by this
    normalization step."""
    cleaned = raw.strip().lower()
    cleaned = cleaned.replace(".", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _strip_spaces_around_symbols(key: str) -> str:
    """Remove spaces adjacent to non-alphanumeric symbols, so "C ++" and
    "CI / CD" match the "c++" and "ci/cd" dictionary aliases. Applied as a
    fallback only — plain space-separated words like "c plus plus" must
    keep their spaces to match their own alias, so this can't be part of
    the primary normalization."""
    return re.sub(r"\s*([^\w\s])\s*", r"\1", key)


def resolve_from_dictionary(raw_skill: str) -> ResolvedSkill | None:
    """Look up a raw skill string in the curated dictionary. Returns None
    if it's not found — the caller should fall back to the LLM for those."""
    key = _normalize_key(raw_skill)
    match = SKILL_LOOKUP.get(key)
    if match is None:
        # Second attempt with symbol-adjacent spaces removed, catching
        # real-world spacing variants like "C ++" or "CI / CD".
        match = SKILL_LOOKUP.get(_strip_spaces_around_symbols(key))
    if match is None:
        return None
    canonical_name, category = match
    return ResolvedSkill(
        raw=raw_skill, canonical_name=canonical_name, category=category, confidence=DICTIONARY_CONFIDENCE
    )
