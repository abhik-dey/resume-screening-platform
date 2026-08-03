"""Abstract repository interface for the canonical Skill directory."""
from abc import ABC, abstractmethod

from app.domain.entities.skill import Skill, SkillCategory


class SkillRepository(ABC):
    @abstractmethod
    async def get_by_name(self, name: str) -> Skill | None:
        """Return the skill with this canonical name (case-insensitive), or None."""

    @abstractmethod
    async def get_or_create(self, name: str, category: SkillCategory) -> Skill:
        """Return the existing skill with this name, or create it if absent."""
