"""
LLM output verification for protected-characteristic language.

CLOSES A GAP flagged in Phases 11 and 12: fairness constraints existed only
in prompts, with nothing checking whether the model complied. A prompt
saying "never mention age" is a request; this is the check.

WHAT IT DOES: scans generated interview questions, feedback, and risk
factors for language referencing protected characteristics before that text
reaches a recruiter. Detection is FLAGGED, not silently removed — a
recruiter needs to know the model produced something questionable, and
silently sanitizing hides a systematic problem.

WHY IT MATTERS MORE HERE THAN ELSEWHERE: interview questions may be read
verbatim to a candidate, and feedback influences hiring decisions. A
question about family status is a discrimination liability regardless of
whether the model "meant" it.

HONEST LIMITATION: keyword matching catches explicit references, not
implication. "Do you have commitments that might affect availability?"
carries no flagged keyword but probes family status. This narrows the gap;
it doesn't close it, which is why human review of generated questions
remains necessary.
"""
import re
from dataclasses import dataclass, field

# Grouped by protected characteristic so a flag says WHICH concern was
# triggered, rather than a generic "problematic content" warning.
_PROTECTED_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("age", re.compile(r"\b(how old|your age|age of|birth\s?date|date of birth|"
                       r"graduat\w+\s+year|too (young|old)|generation)\b", re.IGNORECASE)),
    ("family_status", re.compile(r"\b(married|marital|spouse|husband|wife|children|kids|"
                                 r"pregnan\w+|maternity|paternity|childcare|family plans)\b",
                                 re.IGNORECASE)),
    ("nationality", re.compile(r"\b(where are you from|country of (origin|birth)|"
                               r"native (country|language)|visa status|immigration|citizenship|"
                               r"green card|work permit)\b", re.IGNORECASE)),
    ("religion", re.compile(r"\b(religio\w+|church|mosque|synagogue|temple|faith|"
                            r"religious holiday|sabbath)\b", re.IGNORECASE)),
    # \w* suffixes catch plurals — "medical conditions" was missed by an
    # exact-singular pattern, which is the kind of near-miss that makes a
    # guard look like it works while letting real cases through.
    ("disability", re.compile(r"\b(disabilit\w+|disabled|medical\s+condition\w*|"
                              r"health\s+condition\w*|chronic\s+illness\w*|mental\s+health|"
                              r"therapy|medication\w*)\b",
                              re.IGNORECASE)),
    ("gender", re.compile(r"\b(your gender|gender identity|sexual orientation|"
                          r"pronouns you use)\b", re.IGNORECASE)),
    ("employment_gap_speculation", re.compile(
        r"\b(gap in (your |their )?(employment|career|resume)|why did you leave|"
        r"job.?hopping|frequent job changes)\b", re.IGNORECASE)),
]


@dataclass
class OutputGuardResult:
    flagged: bool
    categories: list[str] = field(default_factory=list)
    flagged_items: list[dict] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.flagged:
            return "No protected-characteristic language detected."
        return (
            f"Generated content references protected characteristics "
            f"({', '.join(self.categories)}). Review before using — questions touching these "
            "areas can expose an employer to discrimination liability."
        )


def scan_output(items: list[str]) -> OutputGuardResult:
    """Scan generated text items for protected-characteristic references."""
    categories: list[str] = []
    flagged_items: list[dict] = []

    for index, item in enumerate(items):
        if not item:
            continue
        hits = [
            category for category, pattern in _PROTECTED_PATTERNS if pattern.search(item)
        ]
        if hits:
            flagged_items.append({"index": index, "text": item[:200], "categories": hits})
            for category in hits:
                if category not in categories:
                    categories.append(category)

    return OutputGuardResult(
        flagged=bool(flagged_items), categories=categories, flagged_items=flagged_items
    )
