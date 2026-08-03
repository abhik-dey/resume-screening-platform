"""
Candidate ranking — pure, deterministic, and fully explainable.

Ranking differs from scoring in a way that matters: scoring evaluates one
resume in isolation, ranking is inherently comparative. That introduces a
problem scoring never had — TIES.

If two candidates both score 0.85, who is #1? Without an explicit rule the
answer would depend on database row order or dict iteration order, meaning
the same data could produce different rankings on different runs. For a
hiring tool that's indefensible, so ties are broken by an explicit,
documented chain ending in a value that is always unique.

TIE-BREAK CHAIN (applied in order):
  1. similarity_score            DESC  -- the primary signal
  2. matched required skill count DESC  -- more required skills met wins
  3. missing required skill count ASC   -- fewer gaps wins
  4. resume_id (as string)        ASC   -- final deterministic fallback

Step 4 is arbitrary in the sense that resume ID carries no merit
information — but it is *deterministic*, which is the property that
matters. An arbitrary-but-stable order beats a non-deterministic one.

COMPETITION RANKING is used for genuine ties: candidates whose full sort
key is identical share a rank, and the next rank skips accordingly
(1, 2, 2, 4 — not 1, 2, 3, 4). This mirrors how sports standings work and
avoids implying a distinction between candidates the system cannot
actually distinguish.

This module is I/O-free and framework-free, so it is fully unit-testable
in isolation.
"""
from dataclasses import dataclass

from app.domain.entities.score import Score


@dataclass
class RankedScore:
    score: Score
    rank: int
    tie_break_reason: str | None = None


def _sort_key(score: Score) -> tuple:
    """The full ordering key. Negated values give DESC ordering while
    keeping the whole key sortable as a single tuple."""
    return (
        -score.similarity_score,
        -len(score.skill_overlap),
        len(score.missing_skills),
        str(score.resume_id),
    )


def _merit_key(score: Score) -> tuple:
    """The portion of the sort key that reflects actual candidate merit,
    excluding the arbitrary resume-ID fallback. Two candidates sharing a
    merit key are genuinely indistinguishable to this system and therefore
    share a rank."""
    return (
        -score.similarity_score,
        -len(score.skill_overlap),
        len(score.missing_skills),
    )


def rank_scores(scores: list[Score]) -> list[RankedScore]:
    """Order scores best-first and assign competition ranks.

    Pure function: the same input list always produces the same output,
    regardless of the input's original order.
    """
    if not scores:
        return []

    ordered = sorted(scores, key=_sort_key)

    ranked: list[RankedScore] = []
    previous_merit_key: tuple | None = None
    current_rank = 0

    for position, score in enumerate(ordered, start=1):
        merit_key = _merit_key(score)
        if merit_key == previous_merit_key:
            # Genuine tie: share the previous rank rather than inventing a
            # distinction the data doesn't support.
            tie_reason = (
                "Tied with the preceding candidate on score, matched skills, and missing skills; "
                "ordered by resume ID for determinism."
            )
        else:
            current_rank = position
            tie_reason = None
            previous_merit_key = merit_key

        ranked.append(RankedScore(score=score, rank=current_rank, tie_break_reason=tie_reason))

    return ranked


def build_ranking_summary(ranked: list[RankedScore]) -> dict:
    """Serializable ordering summary for the audit log — makes the ranking
    decision inspectable after the fact, not just its outcome."""
    return {
        "total_candidates": len(ranked),
        "ordering": [
            {
                "rank": item.rank,
                "resume_id": str(item.score.resume_id),
                "similarity_score": item.score.similarity_score,
                "matched_skills": len(item.score.skill_overlap),
                "missing_skills": len(item.score.missing_skills),
                "tie_break_reason": item.tie_break_reason,
            }
            for item in ranked
        ],
    }
