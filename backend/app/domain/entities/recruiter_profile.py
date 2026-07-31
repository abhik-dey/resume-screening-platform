"""Recruiter-specific profile data, extending a User with role=recruiter."""
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class RecruiterProfile:
    id: UUID
    user_id: UUID
    company_name: str | None
    department: str | None
    phone: str | None
    created_at: datetime
