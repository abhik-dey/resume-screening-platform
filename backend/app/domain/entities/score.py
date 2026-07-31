"""Score domain entity — one per resume, the output of the Matching + Ranking Agents."""
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Score:
    id: UUID
    resume_id: UUID
    job_id: UUID
    similarity_score: float
    skill_overlap: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    rank: int | None = None
    explanation: str | None = None
    created_at: datetime | None = None
