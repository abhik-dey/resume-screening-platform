"""
Text extraction from resume files.

Uses pypdf for PDF and python-docx for DOCX. This is infrastructure, not
domain, because it depends on third-party binary-format-parsing libraries
— but it has no knowledge of LLMs, agents, or the database, so it's kept
as a narrow, single-purpose utility.
"""
import io

import pypdf
from docx import Document


class TextExtractionError(Exception):
    """Raised when a file's text cannot be extracted (corrupted, empty, unsupported)."""


def extract_text(content: bytes, extension: str) -> str:
    """Extract plain text from resume file bytes. `extension` must be
    '.pdf' or '.docx' (already validated at upload time — see Phase 5's
    domain/validation/resume_file.py)."""
    extension = extension.lower()
    if extension == ".pdf":
        text = _extract_pdf_text(content)
    elif extension == ".docx":
        text = _extract_docx_text(content)
    else:
        raise TextExtractionError(f"Unsupported extension for text extraction: {extension}")

    text = text.strip()
    if not text:
        raise TextExtractionError(
            "No extractable text found — the file may be a scanned image with no text layer"
        )
    return text


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)
    except Exception as exc:  # noqa: BLE001 -- any pypdf failure means "can't read this PDF"
        raise TextExtractionError(f"Failed to read PDF content: {exc}") from exc


def _extract_docx_text(content: bytes) -> str:
    try:
        document = Document(io.BytesIO(content))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:  # noqa: BLE001 -- any python-docx failure means "can't read this DOCX"
        raise TextExtractionError(f"Failed to read DOCX content: {exc}") from exc
