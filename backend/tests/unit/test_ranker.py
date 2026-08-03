"""
Tests for the deterministic ranker.

Determinism under ties is the property that matters most here — without an
explicit tie-break, the same data could rank candidates differently on
different runs.
"""
import random
import uuid
from datetime import datetime, timezone

from app.domain.entities.score import Score
from app.domain.matching.ranker import build_ranking_summary, rank_scores


def _make_score(
    similarity: float,
    matched: list[str] | None = None,
    missing: list[str] | None = None,
    resume_id: uuid.UUID | None = None,
) -> Score:
    return Score(
        id=uuid.uuid4(),
        resume_id=resume_id or uuid.uuid4(),
        job_id=uuid.uuid4(),
        similarity_score=similarity,
        skill_overlap=matched if matched is not None else ["Python"],
        missing_skills=missing if missing is not None else [],
        strengths=[],
        weaknesses=[],
        rank=None,
        explanation=None,
        created_at=datetime.now(timezone.utc),
    )


def test_empty_list_returns_empty():
    assert rank_scores([]) == []


def test_single_candidate_gets_rank_one():
    ranked = rank_scores([_make_score(0.5)])
    assert len(ranked) == 1
    assert ranked[0].rank == 1


def test_higher_score_ranks_first():
    low = _make_score(0.4)
    high = _make_score(0.9)
    mid = _make_score(0.6)
    ranked = rank_scores([low, high, mid])
    assert [r.score.similarity_score for r in ranked] == [0.9, 0.6, 0.4]
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_input_order_does_not_affect_output():
    # The same set of candidates must rank identically regardless of the
    # order they arrive in from the database.
    scores = [_make_score(round(random.uniform(0, 1), 3)) for _ in range(10)]

    baseline = [str(r.score.resume_id) for r in rank_scores(list(scores))]
    for _ in range(10):
        shuffled = list(scores)
        random.shuffle(shuffled)
        assert [str(r.score.resume_id) for r in rank_scores(shuffled)] == baseline


def test_identical_candidates_share_a_rank():
    shared_id_a = uuid.UUID("00000000-0000-0000-0000-000000000001")
    shared_id_b = uuid.UUID("00000000-0000-0000-0000-000000000002")
    a = _make_score(0.8, matched=["Python"], missing=[], resume_id=shared_id_a)
    b = _make_score(0.8, matched=["Python"], missing=[], resume_id=shared_id_b)
    ranked = rank_scores([a, b])
    assert [r.rank for r in ranked] == [1, 1]
    assert ranked[1].tie_break_reason is not None


def test_competition_ranking_skips_after_a_tie():
    # Two tied at rank 1 means the next candidate is rank 3, not rank 2 —
    # mirrors sports standings (1, 1, 3) rather than inventing a
    # distinction the data doesn't support.
    a = _make_score(0.9, matched=["Python"], resume_id=uuid.UUID(int=1))
    b = _make_score(0.9, matched=["Python"], resume_id=uuid.UUID(int=2))
    c = _make_score(0.5, matched=["Python"], resume_id=uuid.UUID(int=3))
    ranked = rank_scores([a, b, c])
    assert [r.rank for r in ranked] == [1, 1, 3]


def test_tie_broken_by_matched_skill_count():
    # Same score, but one candidate matched more skills — that candidate
    # wins the tie-break before resume ID is ever consulted.
    fewer = _make_score(0.7, matched=["Python"])
    more = _make_score(0.7, matched=["Python", "SQL", "Go"])
    ranked = rank_scores([fewer, more])
    assert ranked[0].score.skill_overlap == ["Python", "SQL", "Go"]
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
    # Not a genuine tie — merit differed, so no tie-break reason.
    assert ranked[0].tie_break_reason is None


def test_tie_broken_by_fewer_missing_skills():
    many_gaps = _make_score(0.7, matched=["Python"], missing=["Go", "Rust", "C++"])
    few_gaps = _make_score(0.7, matched=["Python"], missing=["Go"])
    ranked = rank_scores([many_gaps, few_gaps])
    assert ranked[0].score.missing_skills == ["Go"]
    assert ranked[0].rank == 1


def test_final_tie_break_is_resume_id_and_is_stable():
    id_low = uuid.UUID("00000000-0000-0000-0000-00000000000a")
    id_high = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    a = _make_score(0.5, resume_id=id_high)
    b = _make_score(0.5, resume_id=id_low)

    for _ in range(20):
        ranked = rank_scores([a, b])
        assert ranked[0].score.resume_id == id_low  # always the same winner


def test_ranks_are_contiguous_when_no_ties():
    scores = [_make_score(s) for s in [0.9, 0.7, 0.5, 0.3]]
    ranked = rank_scores(scores)
    assert [r.rank for r in ranked] == [1, 2, 3, 4]


def test_all_identical_candidates_all_share_rank_one():
    scores = [
        _make_score(0.6, matched=["Python"], missing=[], resume_id=uuid.UUID(int=i))
        for i in range(1, 5)
    ]
    ranked = rank_scores(scores)
    assert [r.rank for r in ranked] == [1, 1, 1, 1]


def test_summary_records_full_ordering_for_audit():
    scores = [_make_score(0.9), _make_score(0.4)]
    summary = build_ranking_summary(rank_scores(scores))
    assert summary["total_candidates"] == 2
    assert len(summary["ordering"]) == 2
    entry = summary["ordering"][0]
    assert {"rank", "resume_id", "similarity_score", "matched_skills", "missing_skills"} <= set(
        entry.keys()
    )
