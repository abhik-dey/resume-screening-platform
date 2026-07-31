"""SQLAlchemy ORM model mapping the `skills` table — the canonical skill directory."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.entities.skill import SkillCategory
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID

if TYPE_CHECKING:
    from app.infrastructure.db.models.resume_skill import ResumeSkillModel


class SkillModel(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Canonical normalized name, e.g. "C++" (never "C Plus Plus") — enforced
    # by the Skill Extraction Agent (Phase 7), not by this table alone.
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    category: Mapped[SkillCategory] = mapped_column(
        SAEnum(
            SkillCategory, values_callable=lambda enum: [e.value for e in enum], native_enum=False, length=20
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resume_links: Mapped[list["ResumeSkillModel"]] = relationship(back_populates="skill")
