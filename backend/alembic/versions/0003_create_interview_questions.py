"""create interview_questions table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03

Added in Phase 11 rather than with the Phase 4 core schema: the Interview
Question Agent is the first consumer of this data, and defining the table
before anything used it would have risked getting its shape wrong.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "resume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_interview_questions_resume_id", "interview_questions", ["resume_id"])
    op.create_index("ix_interview_questions_job_id", "interview_questions", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_interview_questions_job_id", table_name="interview_questions")
    op.drop_index("ix_interview_questions_resume_id", table_name="interview_questions")
    op.drop_table("interview_questions")
