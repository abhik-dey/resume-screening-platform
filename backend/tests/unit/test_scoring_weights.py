"""Tests for recruiter-configurable scoring weights (Phase 10)."""
import pytest

from app.domain.matching.scorer import (
    DEFAULT_WEIGHTS,
    InvalidWeightsError,
    ScoringWeights,
    compute_match_score,
)


def _score(weights=None):
    return compute_match_score(
        candidate_skills=["Python"],
        required_skills=["Python", "Go"],  # 50% skill match
        preferred_skills=[],
        candidate_years_experience=10.0,
        required_years_experience=5,  # fully met
        candidate_education="PhD",
        required_education="Bachelor",  # fully met
        weights=weights,
    )


def test_default_weights_are_the_established_split():
    assert DEFAULT_WEIGHTS.skills == 0.60
    assert DEFAULT_WEIGHTS.experience == 0.25
    assert DEFAULT_WEIGHTS.education == 0.15


def test_omitting_weights_uses_defaults():
    assert _score().overall_score == _score(DEFAULT_WEIGHTS).overall_score


def test_weights_must_sum_to_one():
    with pytest.raises(InvalidWeightsError):
        ScoringWeights(skills=0.5, experience=0.5, education=0.5)
    with pytest.raises(InvalidWeightsError):
        ScoringWeights(skills=0.1, experience=0.1, education=0.1)


def test_negative_weights_rejected():
    with pytest.raises(InvalidWeightsError):
        ScoringWeights(skills=1.2, experience=-0.2, education=0.0)


def test_floating_point_sums_are_tolerated():
    # 0.6 + 0.25 + 0.15 is 0.9999999999999999 in IEEE 754, not exactly 1.0 —
    # exact equality checking would reject perfectly valid weights.
    ScoringWeights(skills=0.6, experience=0.25, education=0.15)
    ScoringWeights(skills=1 / 3, experience=1 / 3, education=1 / 3)


def test_weights_are_immutable():
    weights = ScoringWeights()
    with pytest.raises(Exception):  # noqa: B017 -- dataclasses raises FrozenInstanceError
        weights.skills = 0.9


def test_skill_heavy_weighting_lowers_a_skill_gap_candidate():
    # Candidate has half the required skills but full marks elsewhere.
    # Weighting skills more heavily should lower their overall score.
    balanced = _score(ScoringWeights(skills=0.6, experience=0.25, education=0.15))
    skill_heavy = _score(ScoringWeights(skills=0.9, experience=0.05, education=0.05))
    assert skill_heavy.overall_score < balanced.overall_score


def test_skill_light_weighting_raises_a_skill_gap_candidate():
    balanced = _score(ScoringWeights(skills=0.6, experience=0.25, education=0.15))
    skill_light = _score(ScoringWeights(skills=0.2, experience=0.4, education=0.4))
    assert skill_light.overall_score > balanced.overall_score


def test_zero_weight_component_contributes_nothing():
    result = _score(ScoringWeights(skills=0.0, experience=0.5, education=0.5))
    skills = next(c for c in result.components if c.name == "skills")
    assert skills.weighted_score == 0.0
    # Experience and education both fully met, so the score is 1.0.
    assert result.overall_score == 1.0


def test_custom_weights_are_reflected_in_the_breakdown():
    weights = ScoringWeights(skills=0.8, experience=0.1, education=0.1)
    result = _score(weights)
    by_name = {c.name: c for c in result.components}
    assert by_name["skills"].weight == 0.8
    assert by_name["experience"].weight == 0.1
    assert by_name["education"].weight == 0.1


def test_custom_weighted_scoring_remains_deterministic():
    weights = ScoringWeights(skills=0.7, experience=0.2, education=0.1)
    results = [_score(weights).overall_score for _ in range(30)]
    assert len(set(results)) == 1
