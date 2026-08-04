"""Pydantic schemas for pipeline orchestration."""
from uuid import UUID

from pydantic import BaseModel


class StepDetail(BaseModel):
    success: bool
    reasoning: str


class ResumePipelineResponse(BaseModel):
    resume_id: UUID
    success: bool
    completed_steps: list[str]
    failed_steps: list[str]
    step_details: dict
    halted: bool
    halt_reason: str | None


class JobPipelineResponse(BaseModel):
    job_id: UUID
    total_resumes: int
    successful_resumes: int
    resume_results: list[ResumePipelineResponse]
    ranking_success: bool
    ranking_reasoning: str
    report_success: bool
    report_reasoning: str
    report_id: str | None


class PipelineDescription(BaseModel):
    """Machine-readable pipeline structure, so callers can discover the
    step sequence and failure policy rather than inferring them."""

    steps: list[dict]
    fatal_step_policy: str
