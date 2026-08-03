"""create candidate_feedback table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "candidate_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Unique: one current feedback record per resume. Regenerating
        # replaces it; audit_logs preserves the full history of runs.
        sa.Column(
            "resume_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resumes.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("recommendation", sa.String(length=30), nullable=False),
        sa.Column("threshold_rationale", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("weaknesses", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("risk_factors", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "improvement_suggestions", postgresql.JSONB(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "narrative_generation_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_candidate_feedback_resume_id", "candidate_feedback", ["resume_id"])
    op.create_index("ix_candidate_feedback_job_id", "candidate_feedback", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_candidate_feedback_job_id", table_name="candidate_feedback")
    op.drop_index("ix_candidate_feedback_resume_id", table_name="candidate_feedback")
    op.drop_table("candidate_feedback")
