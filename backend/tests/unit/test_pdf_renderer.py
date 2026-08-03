"""
Tests for PDF rendering.

These generate REAL PDFs and inspect their extracted text — not mocks. A
renderer test that only checks "a function was called" would miss escaping
bugs, missing caveats, and broken layout, which are exactly the failures
that matter for a document a recruiter will read.
"""
import io

import pypdf

from app.domain.report.builder import CandidateRow, ReportData
from app.infrastructure.report.pdf_renderer import render_report_pdf


def _extract_text(pdf_bytes: bytes) -> str:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _page_count(pdf_bytes: bytes) -> int:
    return len(pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages)


def _make_data(**overrides) -> ReportData:
    defaults = {
        "job_title": "Backend Engineer",
        "job_description": "Build APIs.",
        "required_skills": ["Python", "SQL"],
        "preferred_skills": ["Go"],
        "min_experience_years": 5,
        "education_requirement": "Bachelor",
        "candidates": [
            CandidateRow(
                rank=1,
                candidate_name="Jane Doe",
                candidate_email="jane@example.com",
                resume_filename="jane.pdf",
                similarity_score=0.92,
                matched_skills=["Python", "SQL"],
                missing_skills=[],
                recommendation_label="Strong Match",
                threshold_rationale="Score 0.92 meets the strong-recommend threshold.",
                summary="Experienced backend engineer.",
                strengths=["Deep Python knowledge"],
                weaknesses=[],
                risk_factors=[],
            )
        ],
    }
    defaults.update(overrides)
    return ReportData(**defaults)


def test_produces_a_valid_pdf():
    pdf = render_report_pdf(_make_data())
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000


def test_job_title_and_requirements_appear():
    text = _extract_text(render_report_pdf(_make_data()))
    assert "Backend Engineer" in text
    assert "Python" in text


def test_advisory_notice_appears_on_page_one():
    text = _extract_text(render_report_pdf(_make_data()))
    assert "not a hiring decision" in text.lower()


def test_advisory_footer_appears_on_every_page():
    # The most important test in this file. This PDF gets forwarded and
    # printed; a caveat that only appears on page 1 vanishes when someone
    # prints page 3 alone.
    data = _make_data(
        candidates=[
            CandidateRow(
                rank=i,
                candidate_name=f"Candidate {i}",
                candidate_email=None,
                resume_filename=f"c{i}.pdf",
                similarity_score=0.5,
            )
            for i in range(1, 5)
        ]
    )
    pdf = render_report_pdf(data)
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) >= 5
    for page in reader.pages:
        assert "advisory only" in (page.extract_text() or "").lower()


def test_candidate_details_are_rendered():
    text = _extract_text(render_report_pdf(_make_data()))
    assert "Jane Doe" in text
    assert "0.92" in text
    assert "Strong Match" in text
    assert "Deep Python knowledge" in text


def test_html_special_characters_are_escaped_not_interpreted():
    # reportlab parses a subset of HTML in Paragraph text. Unescaped '&' or
    # '<' from a resume would break rendering or be treated as markup.
    data = _make_data(
        candidates=[
            CandidateRow(
                rank=1,
                candidate_name="Smith & Jones <Ltd>",
                candidate_email=None,
                resume_filename="s.pdf",
                similarity_score=0.7,
                summary="Worked at A&B on <critical> systems",
            )
        ]
    )
    text = _extract_text(render_report_pdf(data))
    assert "Smith & Jones <Ltd>" in text
    assert "A&B" in text


def test_empty_candidate_list_still_renders():
    pdf = render_report_pdf(_make_data(candidates=[]))
    text = _extract_text(pdf)
    assert "No scored candidates" in text
    assert pdf[:4] == b"%PDF"


def test_executive_summary_is_included_when_present():
    text = _extract_text(
        render_report_pdf(_make_data(executive_summary="Three strong candidates identified."))
    )
    assert "Three strong candidates identified." in text


def test_failed_summary_is_disclosed_rather_than_hidden():
    text = _extract_text(render_report_pdf(_make_data(summary_generation_failed=True)))
    assert "could not be generated" in text.lower()
    # And it must be clear the candidate data itself is unaffected.
    assert "unaffected" in text.lower()


def test_score_basis_is_explained():
    text = _extract_text(render_report_pdf(_make_data()))
    assert "arithmetically" in text.lower()
    assert "resume-to-requirements fit only" in text.lower()


def test_unranked_candidate_renders_without_error():
    data = _make_data(
        candidates=[
            CandidateRow(
                rank=None,
                candidate_name="Unidentified candidate",
                candidate_email=None,
                resume_filename="x.pdf",
                similarity_score=0.4,
                recommendation_label=None,
            )
        ]
    )
    text = _extract_text(render_report_pdf(data))
    assert "Unidentified candidate" in text
    assert "Not assessed" in text


def test_generated_by_email_appears_when_provided():
    text = _extract_text(render_report_pdf(_make_data(), generated_by_email="rec@company.com"))
    assert "rec@company.com" in text


def test_one_detail_page_per_candidate():
    data = _make_data(
        candidates=[
            CandidateRow(
                rank=i,
                candidate_name=f"Candidate {i}",
                candidate_email=None,
                resume_filename=f"c{i}.pdf",
                similarity_score=0.5,
            )
            for i in range(1, 4)
        ]
    )
    # Page 1 overview + page 2 ranking + one page per candidate.
    assert _page_count(render_report_pdf(data)) == 5
