"""Report domain entity — a recruiter-facing generated PDF summary for a job."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Report:
    id: UUID
    job_id: UUID
    generated_by: UUID
    file_path: str
    summary: str | None = None
    created_at: datetime | None = None
