"""
Text extraction tests using genuinely constructed PDF/DOCX files — not
mocked bytes. reportlab builds a real minimal PDF; python-docx builds a
real minimal DOCX. This proves extract_text() actually reads these formats.
"""
import io

import pytest
from docx import Document
from reportlab.pdfgen import canvas

from app.infrastructure.text_extraction.extractor import TextExtractionError, extract_text


def _build_real_pdf(text: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, text)
    c.save()
    return buffer.getvalue()


def _build_real_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def test_extract_text_from_real_pdf():
    pdf_bytes = _build_real_pdf("Jane Doe - Senior Software Engineer")
    text = extract_text(pdf_bytes, ".pdf")
    assert "Jane Doe" in text
    assert "Senior Software Engineer" in text


def test_extract_text_from_real_docx():
    docx_bytes = _build_real_docx("John Smith - Backend Developer")
    text = extract_text(docx_bytes, ".docx")
    assert "John Smith" in text
    assert "Backend Developer" in text


def test_extract_text_rejects_unsupported_extension():
    with pytest.raises(TextExtractionError):
        extract_text(b"whatever", ".txt")


def test_extract_text_rejects_corrupted_pdf():
    with pytest.raises(TextExtractionError):
        extract_text(b"%PDF-1.4 but actually just garbage after this", ".pdf")


def test_extract_text_rejects_empty_result():
    # A "PDF" with no actual readable text content (e.g. scanned image with
    # no text layer) should fail clearly rather than silently return "".
    blank_pdf = _build_real_pdf("")
    with pytest.raises(TextExtractionError):
        extract_text(blank_pdf, ".pdf")
