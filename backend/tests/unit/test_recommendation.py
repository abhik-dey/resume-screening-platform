"""
Tests for deterministic hiring recommendation derivation.

Threshold boundaries get exhaustive coverage: an off-by-one at a boundary
would silently move real candidates between recommendation categories.
"""
from app.domain.feedback.recommendation import (
    ADVISORY_NOTICE,
    CONSIDER_THRESHOLD,
    RECOMMEND_THRESHOLD,
    STRONG_RECOMMEND_THRESHOLD,
    RecommendationCategory,
    derive_recommendation,
)


def test_strong_recommend_requires_high_score_and_no_missing_required():
    result = derive_recommendation(0.90, [])
    assert result.category == RecommendationCategory.STRONG_RECOMMEND


def test_high_score_with_missing_required_is_capped_at_recommend():
    # A candidate can score well overall while lacking a skill the recruiter
    # marked mandatory — that shouldn't read as a "strong" match.
    result = derive_recommendation(0.90, ["Kubernetes"])
    assert result.category == RecommendationCategory.RECOMMEND
    assert "capped" in result.threshold_rationale.lower()
    assert "Kubernetes" in result.threshold_rationale


def test_recommend_band():
    assert derive_recommendation(0.70, []).category == RecommendationCategory.RECOMMEND


def test_consider_band():
    assert derive_recommendation(0.50, []).category == RecommendationCategory.CONSIDER


def test_not_recommended_band():
    assert derive_recommendation(0.20, []).category == RecommendationCategory.NOT_RECOMMENDED


def test_exact_threshold_boundaries_are_inclusive():
    # >= not >, checked explicitly at each cutoff.
    assert (
        derive_recommendation(STRONG_RECOMMEND_THRESHOLD, []).category
        == RecommendationCategory.STRONG_RECOMMEND
    )
    assert (
        derive_recommendation(RECOMMEND_THRESHOLD, []).category == RecommendationCategory.RECOMMEND
    )
    assert derive_recommendation(CONSIDER_THRESHOLD, []).category == RecommendationCategory.CONSIDER


def test_just_below_each_threshold_falls_to_the_next_band():
    assert derive_recommendation(0.799, []).category == RecommendationCategory.RECOMMEND
    assert derive_recommendation(0.649, []).category == RecommendationCategory.CONSIDER
    assert derive_recommendation(0.449, []).category == RecommendationCategory.NOT_RECOMMENDED


def test_extremes_are_handled():
    assert derive_recommendation(1.0, []).category == RecommendationCategory.STRONG_RECOMMEND
    assert derive_recommendation(0.0, []).category == RecommendationCategory.NOT_RECOMMENDED


def test_derivation_is_deterministic():
    results = [derive_recommendation(0.72, ["Go"]).category for _ in range(50)]
    assert len(set(results)) == 1


def test_every_recommendation_carries_arithmetic_rationale():
    for score in [0.95, 0.70, 0.50, 0.10]:
        result = derive_recommendation(score, [])
        # The rationale must cite the actual number, so "why this category?"
        # is answerable without re-running anything.
        assert f"{score:.2f}" in result.threshold_rationale


def test_not_recommended_rationale_notes_its_limited_scope():
    result = derive_recommendation(0.1, [])
    assert "resume-to-requirements fit only" in result.threshold_rationale


def test_recommendation_is_immutable():
    result = derive_recommendation(0.9, [])
    try:
        result.category = RecommendationCategory.NOT_RECOMMENDED
        raise AssertionError("expected the recommendation to be frozen")
    except AttributeError:
        pass


def test_advisory_notice_states_it_is_not_a_decision():
    lowered = ADVISORY_NOTICE.lower()
    assert "not a hiring decision" in lowered
    assert "human" in lowered
    assert "sole basis" in lowered
