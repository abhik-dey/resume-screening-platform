"""SQLAlchemy ORM model mapping the `resumes` table."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.entities.resume import ResumeStatus
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON

if TYPE_CHECKING:
    from app.infrastructure.db.models.candidate import CandidateModel
    from app.infrastructure.db.models.candidate_feedback import CandidateFeedbackModel
    from app.infrastructure.db.models.interview_question import InterviewQuestionModel
    from app.infrastructure.db.models.job import JobModel
    from app.infrastructure.db.models.resume_skill import ResumeSkillModel
    from app.infrastructure.db.models.score import ScoreModel
    from app.infrastructure.db.models.user import UserModel


class ResumeModel(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    # Nullable: unresolved until the Resume Parsing Agent (Phase 6) extracts
    # the candidate's identity from the uploaded file.
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[dict | None] = mapped_column(PORTABLE_JSON, nullable=True)
    status: Mapped[ResumeStatus] = mapped_column(
        SAEnum(
            ResumeStatus, values_callable=lambda enum: [e.value for e in enum], native_enum=False, length=20
        ),
        default=ResumeStatus.UPLOADED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    candidate: Mapped["CandidateModel | None"] = relationship(back_populates="resumes")
    job: Mapped["JobModel"] = relationship(back_populates="resumes")
    uploaded_by_user: Mapped["UserModel"] = relationship(back_populates="resumes_uploaded")
    skills: Mapped[list["ResumeSkillModel"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    score: Mapped["ScoreModel | None"] = relationship(
        back_populates="resume", uselist=False, cascade="all, delete-orphan"
    )
    interview_questions: Mapped[list["InterviewQuestionModel"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    feedback: Mapped["CandidateFeedbackModel | None"] = relationship(
        back_populates="resume", uselist=False, cascade="all, delete-orphan"
    )
