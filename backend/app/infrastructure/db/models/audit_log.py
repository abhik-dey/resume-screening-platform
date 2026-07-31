"""
SQLAlchemy ORM model mapping the `audit_logs` table.

Design decision: NO foreign keys to other tables. `input_ref` is a plain
string (e.g. "resume:3fae21..."), not a relationship. An audit/compliance
trail needs to survive independently of the business data it describes —
deleting a resume should never cascade-delete (or be blocked by) the audit
rows that reference it. This is the standard pattern for audit log tables.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base
from app.infrastructure.db.types import GUID, PORTABLE_JSON


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    input_ref: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    output: Mapped[dict | None] = mapped_column(PORTABLE_JSON, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
