"""SQLAlchemy ORM model mapping the `candidates` table."""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON

if TYPE_CHECKING:
    from app.infrastructure.db.models.resume import ResumeModel


class CandidateModel(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    links: Mapped[dict] = mapped_column(PORTABLE_JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    resumes: Mapped[list["ResumeModel"]] = relationship(back_populates="candidate")
