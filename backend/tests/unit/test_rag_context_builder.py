"""Tests for RAG context assembly."""
from app.domain.rag.context_builder import (
    MAX_CHARS_PER_SOURCE,
    MAX_CONTEXT_CHARS,
    build_source_chunks,
    format_context,
)


def _hit(text="Skills: Python", name="Jane Doe", similarity=0.9, resume_id="r1"):
    return {"resume_id": resume_id, "candidate_name": name, "similarity": similarity, "text": text}


def test_chunks_are_numbered_from_one():
    chunks = build_source_chunks([_hit(resume_id="a"), _hit(resume_id="b"), _hit(resume_id="c")])
    assert [c.source_id for c in chunks] == [1, 2, 3]


def test_retrieval_order_is_preserved():
    # Source [1] must be the strongest match, since the model is likely to
    # weight earlier sources more heavily.
    chunks = build_source_chunks(
        [_hit(resume_id="best", similarity=0.9), _hit(resume_id="worst", similarity=0.2)]
    )
    assert chunks[0].resume_id == "best"


def test_empty_input_produces_no_chunks():
    assert build_source_chunks([]) == []


def test_hits_with_no_text_are_skipped():
    chunks = build_source_chunks([_hit(text="  ", resume_id="empty"), _hit(resume_id="ok")])
    assert len(chunks) == 1
    assert chunks[0].resume_id == "ok"
    # Numbering stays contiguous despite the skip.
    assert chunks[0].source_id == 1


def test_oversized_source_is_truncated_with_a_marker():
    chunks = build_source_chunks([_hit(text="x" * (MAX_CHARS_PER_SOURCE + 500))])
    assert "[...truncated]" in chunks[0].text


def test_total_budget_drops_sources_rather_than_cutting_mid_resume():
    # A half-cut resume could read as though a candidate lacks experience
    # that was simply cut off — dropping whole sources is safer.
    big = "y" * MAX_CHARS_PER_SOURCE
    chunks = build_source_chunks([_hit(text=big, resume_id=str(i)) for i in range(20)])
    total = sum(len(c.text) for c in chunks)
    assert total <= MAX_CONTEXT_CHARS
    assert len(chunks) < 20


def test_missing_candidate_name_falls_back_to_a_placeholder():
    chunks = build_source_chunks([{"resume_id": "r1", "similarity": 0.5, "text": "Skills: Go"}])
    assert chunks[0].candidate_name == "Unidentified candidate"


def test_format_context_includes_numbered_markers():
    chunks = build_source_chunks([_hit(name="Alice"), _hit(name="Bob", resume_id="r2")])
    formatted = format_context(chunks)
    assert "[1] Candidate: Alice" in formatted
    assert "[2] Candidate: Bob" in formatted


def test_format_context_handles_no_chunks():
    assert "No sources" in format_context([])
