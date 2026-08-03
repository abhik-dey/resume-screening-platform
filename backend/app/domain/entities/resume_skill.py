"""Read-model entity combining a resume's linked skill with its details —
used when listing a resume's skills (joins resume_skills + skills)."""
from dataclasses import dataclass
from uuid import UUID

from app.domain.entities.skill import SkillCategory


@dataclass
class ResumeSkillDetail:
    skill_id: UUID
    name: str
    category: SkillCategory
    confidence: float | None
