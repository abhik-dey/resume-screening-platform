"""
Tests for citation validation — the groundedness enforcement mechanism.

These matter more than most: this is the code standing between an LLM's
confident fabrication about a real person and a recruiter reading it as fact.
"""
from app.domain.rag.citation_validator import (
    extract_inline_citations,
    validate_claims,
)

VALID_IDS = {1, 2, 3}


def test_properly_cited_claim_is_grounded():
    result = validate_claims(
        [{"text": "Jane has Kubernetes experience.", "source_ids": [1]}], VALID_IDS
    )
    assert len(result.grounded_claims) == 1
    assert result.grounded_claims[0].source_ids == [1]
    assert result.warnings == []


def test_uncited_claim_is_rejected():
    # An uncited claim is unverifiable, which in this context means unusable.
    result = validate_claims([{"text": "Jane is a strong candidate.", "source_ids": []}], VALID_IDS)
    assert result.grounded_claims == []
    assert len(result.ungrounded_claims) == 1
    assert "no citation" in result.ungrounded_claims[0].warning.lower()
    assert result.warnings


def test_claim_citing_a_nonexistent_source_is_rejected():
    # The core failure mode: the model invents a source to support a claim.
    result = validate_claims(
        [{"text": "Jane has 8 years of Kubernetes experience.", "source_ids": [99]}], VALID_IDS
    )
    assert result.grounded_claims == []
    assert "do not exist" in result.ungrounded_claims[0].warning


def test_claim_with_mixed_real_and_fake_citations_is_kept_but_flagged():
    result = validate_claims(
        [{"text": "Two candidates know Terraform.", "source_ids": [1, 99]}], VALID_IDS
    )
    assert len(result.grounded_claims) == 1
    # The fabricated ID is dropped, the real one retained.
    assert result.grounded_claims[0].source_ids == [1]
    assert "99" in result.grounded_claims[0].warning
    assert result.warnings


def test_multiple_valid_citations_are_all_kept():
    result = validate_claims(
        [{"text": "Three candidates use Python.", "source_ids": [1, 2, 3]}], VALID_IDS
    )
    assert result.grounded_claims[0].source_ids == [1, 2, 3]


def test_duplicate_citations_are_deduplicated():
    result = validate_claims([{"text": "Claim.", "source_ids": [1, 1, 2]}], VALID_IDS)
    assert result.grounded_claims[0].source_ids == [1, 2]


def test_inline_citations_are_recovered_when_structured_field_is_empty():
    # Models often cite in prose rather than populating the schema field;
    # rejecting those would discard genuinely grounded claims.
    result = validate_claims(
        [{"text": "Jane has Kubernetes experience [1].", "source_ids": []}], VALID_IDS
    )
    assert len(result.grounded_claims) == 1
    assert result.grounded_claims[0].source_ids == [1]


def test_inline_citation_extraction_handles_formats():
    assert extract_inline_citations("Claim [1].") == [1]
    assert extract_inline_citations("Claim [1, 2].") == [1, 2]
    assert extract_inline_citations("Claim [1][3].") == [1, 3]
    assert extract_inline_citations("No citation here.") == []


def test_string_source_ids_are_accepted():
    # LLMs frequently return "1" rather than 1 despite the schema.
    result = validate_claims([{"text": "Claim.", "source_ids": ["1", "2"]}], VALID_IDS)
    assert result.grounded_claims[0].source_ids == [1, 2]


def test_empty_text_claims_are_skipped():
    result = validate_claims([{"text": "   ", "source_ids": [1]}], VALID_IDS)
    assert result.claims == []


def test_all_claims_ungrounded_is_detected():
    # The caller needs to know when NOTHING survived, so it can reject the
    # whole answer rather than showing a hollowed-out version.
    result = validate_claims(
        [
            {"text": "Fabricated claim one.", "source_ids": [99]},
            {"text": "Fabricated claim two.", "source_ids": []},
        ],
        VALID_IDS,
    )
    assert result.all_claims_ungrounded is True


def test_partially_grounded_answer_is_not_flagged_as_fully_ungrounded():
    result = validate_claims(
        [
            {"text": "Grounded claim.", "source_ids": [1]},
            {"text": "Fabricated claim.", "source_ids": [99]},
        ],
        VALID_IDS,
    )
    assert result.all_claims_ungrounded is False
    assert len(result.grounded_claims) == 1
    assert len(result.ungrounded_claims) == 1


def test_empty_claim_list_is_not_flagged_as_ungrounded():
    # No claims at all is different from all claims failing validation.
    result = validate_claims([], VALID_IDS)
    assert result.all_claims_ungrounded is False


def test_no_valid_sources_rejects_everything():
    result = validate_claims([{"text": "Claim.", "source_ids": [1]}], set())
    assert result.grounded_claims == []
