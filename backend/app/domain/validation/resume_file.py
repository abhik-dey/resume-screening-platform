"""
Resume file validation — a pure domain rule.

Deliberately framework-agnostic and I/O-free: no FastAPI, no filesystem
access, no database. Given raw bytes and a filename, this decides whether
a file is acceptable as a resume upload. That makes it fully unit-testable
without spinning up an API, a database, or touching disk.

Validates the ACTUAL FILE CONTENT (magic bytes), not just the filename
extension — renaming malware.exe to resume.pdf does not pass this check.
"""
from dataclasses import dataclass

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

# Magic bytes: the first few bytes of a file that identify its true format,
# regardless of what its filename claims. PDFs start with the literal
# bytes "%PDF". DOCX files are actually ZIP archives (Office Open XML),
# so they start with the ZIP local-file-header signature "PK\x03\x04".
_MAGIC_BYTES: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".docx": b"PK\x03\x04",
}


class ResumeValidationError(Exception):
    """Base class for all resume file validation failures."""


class EmptyFileError(ResumeValidationError):
    def __init__(self) -> None:
        super().__init__("Uploaded file is empty")


class FileTooLargeError(ResumeValidationError):
    def __init__(self, size_bytes: int, max_size_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_size_bytes = max_size_bytes
        super().__init__(
            f"File is {size_bytes} bytes, exceeding the {max_size_bytes}-byte limit"
        )


class UnsupportedFileTypeError(ResumeValidationError):
    def __init__(self, extension: str) -> None:
        self.extension = extension
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        super().__init__(f"Unsupported file type '{extension}'. Allowed types: {allowed}")


class FileContentMismatchError(ResumeValidationError):
    """Raised when a file's actual content doesn't match its claimed extension —
    e.g. a .pdf filename wrapping a file that isn't really a PDF."""

    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(
            f"File content does not match its '{extension}' extension "
            "(the file may be corrupted, mislabeled, or disguised)"
        )


@dataclass
class ValidatedFile:
    """Result of a successful validation — the extension is normalized (lowercase)."""

    extension: str
    size_bytes: int


def validate_resume_file(filename: str, content: bytes, max_size_bytes: int) -> ValidatedFile:
    """Validate a resume upload. Raises a ResumeValidationError subclass on failure."""
    if len(content) == 0:
        raise EmptyFileError()

    if len(content) > max_size_bytes:
        raise FileTooLargeError(size_bytes=len(content), max_size_bytes=max_size_bytes)

    extension = _extract_extension(filename)
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    expected_magic = _MAGIC_BYTES[extension]
    if not content.startswith(expected_magic):
        raise FileContentMismatchError(extension)

    return ValidatedFile(extension=extension, size_bytes=len(content))


def _extract_extension(filename: str) -> str:
    # Strip any path components a malicious client might smuggle in
    # (e.g. "../../etc/passwd.pdf") — we only ever look at the final
    # segment, and the storage layer never trusts this filename for
    # the actual on-disk path anyway (see LocalFileStorage).
    base = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if "." not in base:
        return ""
    return "." + base.rsplit(".", 1)[-1].lower()
