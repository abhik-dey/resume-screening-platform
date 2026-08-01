import pytest

from app.domain.validation.resume_file import (
    EmptyFileError,
    FileContentMismatchError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    validate_resume_file,
)

MAX_SIZE = 10 * 1024 * 1024  # 10 MB


def test_valid_pdf_passes():
    content = b"%PDF-1.4 minimal fake pdf content"
    result = validate_resume_file("resume.pdf", content, MAX_SIZE)
    assert result.extension == ".pdf"
    assert result.size_bytes == len(content)


def test_valid_docx_passes():
    content = b"PK\x03\x04 minimal fake docx (zip) content"
    result = validate_resume_file("resume.docx", content, MAX_SIZE)
    assert result.extension == ".docx"


def test_empty_file_rejected():
    with pytest.raises(EmptyFileError):
        validate_resume_file("resume.pdf", b"", MAX_SIZE)


def test_oversized_file_rejected():
    content = b"%PDF" + b"0" * MAX_SIZE
    with pytest.raises(FileTooLargeError):
        validate_resume_file("resume.pdf", content, MAX_SIZE)


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedFileTypeError):
        validate_resume_file("resume.exe", b"MZ fake exe content", MAX_SIZE)


def test_missing_extension_rejected():
    with pytest.raises(UnsupportedFileTypeError):
        validate_resume_file("resume", b"%PDF content", MAX_SIZE)


def test_content_mismatch_rejected():
    # A .pdf filename wrapping content that isn't actually a PDF —
    # e.g. a renamed executable trying to disguise itself.
    with pytest.raises(FileContentMismatchError):
        validate_resume_file("resume.pdf", b"MZ this is not a pdf", MAX_SIZE)


def test_path_traversal_filename_still_extracts_correct_extension():
    # The extension check should look only at the final path segment.
    content = b"%PDF fake content"
    result = validate_resume_file("../../etc/passwd.pdf", content, MAX_SIZE)
    assert result.extension == ".pdf"
