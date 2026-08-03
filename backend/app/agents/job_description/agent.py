"""
Job Description Agent.

Pipeline step 3 (per the Phase 1 LangGraph flow): Skill Extraction Agent ->
Job Description Agent -> Matching Agent -> ...

Given a job_id, this agent:
1. Sends the job's free-text description to the LLM for structured extraction
2. Normalizes extracted skills through the SAME dictionary the Skill
   Extraction Agent uses (Phase 7) — this is essential, not cosmetic: if a
   job says "postgres" and a resume says "PostgreSQL", the Matching Agent
   (Phase 9) must see one canonical name or every score would be wrong
3. Merges the results into the job WITHOUT clobbering values a recruiter
   explicitly set (see MERGE POLICY below)

MERGE POLICY
------------
An LLM's guess must never silently overwrite a human's deliberate input.
  - Field is empty        -> apply the extracted value
  - Field already has data -> keep the recruiter's, report the extracted
                              value as a suggestion only
  - overwrite=True         -> apply extracted values regardless (opt-in,
                              for recruiters who want the agent's version)

The audit log records BOTH what was extracted and what was actually
applied, so any divergence between the two remains fully traceable.
"""
import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.agents.job_description.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.job_description.schemas import JobRequirementsOutput
from app.agents.llm_json_utils import call_llm_for_json
from app.domain.entities.job import Job
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.skills.normalizer import resolve_from_dictionary

MAX_LLM_ATTEMPTS = 2


class JobDescriptionAnalysisError(Exception):
    """Raised when analysis cannot be completed."""


def _normalize_skill_list(raw_skills: list[str]) -> list[str]:
    """Canonicalize skill names against the shared dictionary, preserving
    order and removing duplicates that collapse to the same canonical name.
    Unknown skills are kept as-is (title-cased) rather than dropped — a job
    requiring a niche in-house tool is still a real requirement."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in raw_skills:
        hit = resolve_from_dictionary(raw)
        name = hit.canonical_name if hit else raw.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(name)
    return normalized


class JobDescriptionAgent(BaseAgent):
    agent_name = "job_description"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        job_repository: JobRepository,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._jobs = job_repository
        self._llm = llm_provider

    async def analyze(self, job_id: uuid.UUID, overwrite: bool = False):
        """Public entrypoint — wraps `run()` with the job's audit input_ref."""
        return await self.run(input_ref=f"job:{job_id}", job_id=job_id, overwrite=overwrite)

    async def _execute(self, job_id: uuid.UUID, overwrite: bool) -> tuple[dict[str, Any], str]:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise JobDescriptionAnalysisError(f"Job {job_id} not found")
        if not job.description.strip():
            raise JobDescriptionAnalysisError(f"Job {job_id} has an empty description — nothing to analyze")

        extracted = await self._call_llm(job.title, job.description)
        if extracted is None:
            raise JobDescriptionAnalysisError(
                f"LLM did not return valid structured output after {MAX_LLM_ATTEMPTS} attempts"
            )

        extracted.required_skills = _normalize_skill_list(extracted.required_skills)
        extracted.preferred_skills = _normalize_skill_list(extracted.preferred_skills)

        applied_fields, skipped_fields = self._merge_into_job(job, extracted, overwrite)
        if applied_fields:
            await self._jobs.update(job)

        output = {
            "extracted": extracted.model_dump(mode="json"),
            "applied_fields": applied_fields,
            "skipped_fields": skipped_fields,
        }
        reasoning = (
            f"Extracted {len(extracted.required_skills)} required and "
            f"{len(extracted.preferred_skills)} preferred skills, "
            f"{len(extracted.responsibilities)} responsibilities. "
            f"Applied {len(applied_fields)} field(s): {', '.join(applied_fields) or 'none'}."
        )
        if skipped_fields:
            reasoning += (
                f" Left {len(skipped_fields)} recruiter-provided field(s) untouched: "
                f"{', '.join(skipped_fields)}. Pass overwrite=true to replace them."
            )
        return output, reasoning

    def _merge_into_job(
        self, job: Job, extracted: JobRequirementsOutput, overwrite: bool
    ) -> tuple[list[str], list[str]]:
        """Mutate `job` in place per the merge policy. Returns
        (applied_field_names, skipped_field_names)."""
        applied: list[str] = []
        skipped: list[str] = []

        # (field_name, current_value, extracted_value, is_empty_check)
        candidates: list[tuple[str, Any, Any]] = [
            ("required_skills", job.required_skills, extracted.required_skills),
            ("preferred_skills", job.preferred_skills, extracted.preferred_skills),
            ("min_experience_years", job.min_experience_years, extracted.min_experience_years),
            ("education_requirement", job.education_requirement, extracted.education_requirement),
            ("responsibilities", job.responsibilities, extracted.responsibilities),
            ("keywords", job.keywords, extracted.keywords),
        ]

        for field_name, current_value, extracted_value in candidates:
            # Nothing extracted for this field — never overwrite existing
            # data with emptiness, even when overwrite=True. "The LLM found
            # nothing" is not a reason to erase what a recruiter typed.
            if extracted_value is None or (isinstance(extracted_value, list) and not extracted_value):
                continue

            current_is_empty = current_value is None or (
                isinstance(current_value, list) and not current_value
            )
            if current_is_empty or overwrite:
                setattr(job, field_name, extracted_value)
                applied.append(field_name)
            else:
                skipped.append(field_name)

        return applied, skipped

    async def _call_llm(self, title: str, description: str) -> JobRequirementsOutput | None:
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(title, description),
            validate=JobRequirementsOutput.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
