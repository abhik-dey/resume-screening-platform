"""Skill domain entity — a canonical, normalized skill name."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class SkillCategory(str, Enum):
    PROGRAMMING = "programming"
    CLOUD = "cloud"
    DATABASES = "databases"
    AI = "ai"
    DEVOPS = "devops"
    SOFT_SKILLS = "soft_skills"


@dataclass
class Skill:
    id: UUID
    name: str
    category: SkillCategory
    created_at: datetime | None = None
