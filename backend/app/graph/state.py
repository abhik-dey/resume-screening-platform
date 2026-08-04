"""
Pipeline state passed between LangGraph nodes.

Explicit and typed rather than a loose dict: what flows between agents is
the contract of the pipeline, and leaving it untyped would make the
orchestration exactly as opaque as the manual call sequence it replaces.

LangGraph merges partial updates returned by each node into this structure,
so nodes return only what they changed.
"""
from typing import Annotated, TypedDict
from uuid import UUID


def _append(existing: list, new: list) -> list:
    """Reducer telling LangGraph to accumulate list fields across nodes
    rather than have each node's return overwrite the previous value."""
    return (existing or []) + (new or [])


def _merge(existing: dict, new: dict) -> dict:
    return {**(existing or {}), **(new or {})}


class PipelineState(TypedDict, total=False):
    resume_id: UUID
    job_id: UUID | None

    # Ordered record of what ran successfully.
    completed_steps: Annotated[list[str], _append]
    # Steps that failed. A step can fail without halting the pipeline —
    # see the fatal/non-fatal distinction in pipeline.py.
    failed_steps: Annotated[list[str], _append]
    # Per-step reasoning and output, so a completed run is inspectable
    # without cross-referencing the audit log.
    step_details: Annotated[dict[str, dict], _merge]

    # Set when a prerequisite step fails. Downstream nodes short-circuit
    # rather than running against data that isn't there.
    halted: bool
    halt_reason: str | None


def initial_state(resume_id: UUID, job_id: UUID | None = None) -> PipelineState:
    return PipelineState(
        resume_id=resume_id,
        job_id=job_id,
        completed_steps=[],
        failed_steps=[],
        step_details={},
        halted=False,
        halt_reason=None,
    )
