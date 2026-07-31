"""Resume domain entity — one per candidate-job application."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ResumeStatus(str, Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


@dataclass
class Resume:
    id: UUID
    job_id: UUID
    uploaded_by: UUID
    storage_path: str
    original_filename: str
    # candidate_id is unresolved at upload time — the Resume Parsing Agent
    # (Phase 6) extracts the candidate's identity from the file contents.
    candidate_id: UUID | None = None
    raw_text: str | None = None
    parsed_data: dict | None = None
    status: ResumeStatus = ResumeStatus.UPLOADED
    created_at: datetime | None = None
