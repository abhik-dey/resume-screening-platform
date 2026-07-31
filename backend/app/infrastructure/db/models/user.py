"""SQLAlchemy ORM model mapping the `users` table."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.entities.user import UserRole
from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID

if TYPE_CHECKING:
    from app.infrastructure.db.models.job import JobModel
    from app.infrastructure.db.models.recruiter_profile import RecruiterProfileModel
    from app.infrastructure.db.models.report import ReportModel
    from app.infrastructure.db.models.resume import ResumeModel


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Stored as VARCHAR (native_enum=False) rather than a Postgres native ENUM type,
    # so adding a new role later is a simple data migration, not a schema-altering
    # `ALTER TYPE` — and it keeps this column portable to the SQLite test database.
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, values_callable=lambda enum: [e.value for e in enum], native_enum=False, length=20),
        default=UserRole.RECRUITER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    recruiter_profile: Mapped["RecruiterProfileModel | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    jobs_created: Mapped[list["JobModel"]] = relationship(back_populates="creator")
    resumes_uploaded: Mapped[list["ResumeModel"]] = relationship(back_populates="uploaded_by_user")
    reports_generated: Mapped[list["ReportModel"]] = relationship(back_populates="generated_by_user")
