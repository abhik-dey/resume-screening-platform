"""SQLAlchemy ORM model mapping the `jobs` table."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.entities.job import JobStatus
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON

if TYPE_CHECKING:
    from app.infrastructure.db.models.interview_question import InterviewQuestionModel
    from app.infrastructure.db.models.report import ReportModel
    from app.infrastructure.db.models.resume import ResumeModel
    from app.infrastructure.db.models.score import ScoreModel
    from app.infrastructure.db.models.user import UserModel


class JobModel(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    required_skills: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    preferred_skills: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    min_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsibilities: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(PORTABLE_JSON, default=list, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, values_callable=lambda enum: [e.value for e in enum], native_enum=False, length=20),
        default=JobStatus.DRAFT,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    creator: Mapped["UserModel"] = relationship(back_populates="jobs_created")
    resumes: Mapped[list["ResumeModel"]] = relationship(back_populates="job")
    scores: Mapped[list["ScoreModel"]] = relationship(back_populates="job")
    reports: Mapped[list["ReportModel"]] = relationship(back_populates="job")
    interview_questions: Mapped[list["InterviewQuestionModel"]] = relationship(back_populates="job")
