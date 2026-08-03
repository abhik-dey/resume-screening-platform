"""Tests for pure report data assembly."""
import uuid
from datetime import datetime, timezone

from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.score import Score
from app.domain.feedback.recommendation import RecommendationCategory
from app.domain.report.builder import assemble_report_data


def _make_job() -> Job:
    return Job(
        id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs.",
        required_skills=["Python", "SQL"],
        preferred_skills=["Go"],
        min_experience_years=5,
        education_requirement="Bachelor",
        status=JobStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )


def _make_score(resume_id, similarity, rank=None, missing=None) -> Score:
    return Score(
        id=uuid.uuid4(),
        resume_id=resume_id,
        job_id=uuid.uuid4(),
        similarity_score=similarity,
        skill_overlap=["Python"],
        missing_skills=missing or [],
        strengths=[],
        weaknesses=[],
        rank=rank,
        explanation=None,
        created_at=datetime.now(timezone.utc),
    )


def _make_feedback(resume_id, category=RecommendationCategory.RECOMMEND) -> CandidateFeedback:
    return CandidateFeedback(
        id=uuid.uuid4(),
        resume_id=resume_id,
        job_id=uuid.uuid4(),
        recommendation=category,
        threshold_rationale="Rationale text.",
        summary="Candidate summary.",
        strengths=["Strong Python"],
        weaknesses=["Limited infra"],
        risk_factors=[],
        created_at=datetime.now(timezone.utc),
    )


def test_empty_candidate_list_produces_valid_data():
    data = assemble_report_data(_make_job(), [], {}, {}, {})
    assert data.total_candidates == 0
    assert data.average_score == 0.0
    assert data.recommendation_counts == {}


def test_candidates_ordered_by_rank():
    ids = [uuid.uuid4() for _ in range(3)]
    scores = [
        _make_score(ids[0], 0.5, rank=3),
        _make_score(ids[1], 0.9, rank=1),
        _make_score(ids[2], 0.7, rank=2),
    ]
    data = assemble_report_data(_make_job(), scores, {}, {}, {})
    assert [c.rank for c in data.candidates] == [1, 2, 3]


def test_unranked_candidates_sort_last():
    ids = [uuid.uuid4() for _ in range(3)]
    scores = [
        _make_score(ids[0], 0.95, rank=None),
        _make_score(ids[1], 0.5, rank=1),
        _make_score(ids[2], 0.4, rank=2),
    ]
    data = assemble_report_data(_make_job(), scores, {}, {}, {})
    # Even with the highest score, an unranked candidate goes last —
    # ranking is authoritative once it has run.
    assert [c.rank for c in data.candidates] == [1, 2, None]


def test_ordering_is_deterministic_regardless_of_input_order():
    ids = [uuid.uuid4() for _ in range(4)]
    scores = [_make_score(i, 0.5, rank=None) for i in ids]
    filenames = {i: f"resume{n}.pdf" for n, i in enumerate(ids)}

    baseline_data = assemble_report_data(_make_job(), scores, filenames, {}, {})
    baseline = [c.resume_filename for c in baseline_data.candidates]
    for _ in range(5):
        reversed_scores = list(reversed(scores))
        result = [
            c.resume_filename
            for c in assemble_report_data(_make_job(), reversed_scores, filenames, {}, {}).candidates
        ]
        assert result == baseline


def test_candidates_without_feedback_are_still_included():
    # Omitting them would misrepresent how many people applied.
    resume_id = uuid.uuid4()
    data = assemble_report_data(_make_job(), [_make_score(resume_id, 0.6)], {}, {}, {})
    assert data.total_candidates == 1
    assert data.candidates[0].recommendation_label is None


def test_candidate_details_are_joined_in():
    resume_id = uuid.uuid4()
    data = assemble_report_data(
        _make_job(),
        [_make_score(resume_id, 0.6)],
        {resume_id: "jane.pdf"},
        {resume_id: {"full_name": "Jane Doe", "email": "jane@example.com"}},
        {},
    )
    row = data.candidates[0]
    assert row.candidate_name == "Jane Doe"
    assert row.candidate_email == "jane@example.com"
    assert row.resume_filename == "jane.pdf"


def test_unidentified_candidate_gets_a_placeholder_name():
    # candidate_id is nullable until parsing resolves it (Phase 4/6).
    resume_id = uuid.uuid4()
    data = assemble_report_data(_make_job(), [_make_score(resume_id, 0.6)], {}, {}, {})
    assert data.candidates[0].candidate_name == "Unidentified candidate"


def test_feedback_is_joined_in_with_readable_labels():
    resume_id = uuid.uuid4()
    data = assemble_report_data(
        _make_job(),
        [_make_score(resume_id, 0.9)],
        {},
        {},
        {resume_id: _make_feedback(resume_id, RecommendationCategory.STRONG_RECOMMEND)},
    )
    row = data.candidates[0]
    assert row.recommendation_label == "Strong Match"
    assert row.summary == "Candidate summary."
    assert row.strengths == ["Strong Python"]


def test_average_score_calculation():
    ids = [uuid.uuid4() for _ in range(3)]
    scores = [_make_score(ids[0], 0.9), _make_score(ids[1], 0.6), _make_score(ids[2], 0.3)]
    data = assemble_report_data(_make_job(), scores, {}, {}, {})
    assert data.average_score == 0.6


def test_recommendation_counts_aggregate_correctly():
    ids = [uuid.uuid4() for _ in range(3)]
    scores = [_make_score(i, 0.7) for i in ids]
    feedback = {
        ids[0]: _make_feedback(ids[0], RecommendationCategory.STRONG_RECOMMEND),
        ids[1]: _make_feedback(ids[1], RecommendationCategory.RECOMMEND),
        ids[2]: _make_feedback(ids[2], RecommendationCategory.RECOMMEND),
    }
    data = assemble_report_data(_make_job(), scores, {}, {}, feedback)
    assert data.recommendation_counts == {"Strong Match": 1, "Recommended": 2}


def test_job_requirements_are_carried_through():
    data = assemble_report_data(_make_job(), [], {}, {}, {})
    assert data.required_skills == ["Python", "SQL"]
    assert data.preferred_skills == ["Go"]
    assert data.min_experience_years == 5
    assert data.education_requirement == "Bachelor"
