"""Candidate domain entity — a deduplicated person identity, resolved from resumes."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Candidate:
    id: UUID
    full_name: str
    email: str
    phone: str | None = None
    links: dict[str, str] = field(default_factory=dict)
    created_at: datetime | None = None
