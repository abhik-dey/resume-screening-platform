"""
SQLAlchemy ORM model mapping the `resume_skills` table.

Note: named `resume_skills`, not `candidate_skills` as in the original spec
— see the Phase 4 design note on why skills are resume-scoped rather than
candidate-scoped. Uses a composite primary key (resume_id, skill_id) since
this is a genuine many-to-many association with an extra attribute
(confidence), not an independent entity needing its own surrogate key.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID

if TYPE_CHECKING:
    from app.infrastructure.db.models.resume import ResumeModel
    from app.infrastructure.db.models.skill import SkillModel


class ResumeSkillModel(Base):
    __tablename__ = "resume_skills"

    resume_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resumes.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True
    )
    # Confidence from the Skill Extraction Agent (Phase 7), e.g. 0.0-1.0.
    # Nullable because manually-added skills (later phase) won't have one.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    resume: Mapped["ResumeModel"] = relationship(back_populates="skills")
    skill: Mapped["SkillModel"] = relationship(back_populates="resume_links")
