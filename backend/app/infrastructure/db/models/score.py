"""SQLAlchemy ORM model mapping the `scores` table — Matching + Ranking Agent output."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON

if TYPE_CHECKING:
    from app.infrastructure.db.models.job import JobModel
    from app.infrastructure.db.models.resume import ResumeModel


class ScoreModel(Base):
    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # unique=True: a resume belongs to exactly one job, so it can have at
    # most one score row — this is a genuine 1:1, not 1:N.
    resume_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("resumes.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Denormalized from resume.job_id: lets the Ranking Agent query
    # "all scores for job X, ordered by rank" without a join.
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    skill_overlap: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    missing_skills: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    strengths: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    weaknesses: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    # Set later, by the Ranking Agent, once all resumes for a job are scored.
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resume: Mapped["ResumeModel"] = relationship(back_populates="score")
    job: Mapped["JobModel"] = relationship(back_populates="scores")
