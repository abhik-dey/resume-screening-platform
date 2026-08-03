"""Structured output schema for the Skill Extraction Agent's LLM fallback call."""
from pydantic import BaseModel, Field

from app.domain.entities.skill import SkillCategory


class CategorizedSkill(BaseModel):
    raw: str
    canonical_name: str
    category: SkillCategory


class SkillCategorizationOutput(BaseModel):
    skills: list[CategorizedSkill] = Field(default_factory=list)
