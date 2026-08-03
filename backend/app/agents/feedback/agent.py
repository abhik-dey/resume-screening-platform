"""
Feedback Agent.

Pipeline step 7 (per the Phase 1 LangGraph flow): Interview Question Agent ->
Feedback Agent -> Report Generator.

Produces a candidate summary, hiring recommendation, risk factors, strengths,
weaknesses, and improvement suggestions.

DESIGN: the recommendation CATEGORY is derived arithmetically from the Phase 9
match score (see domain/feedback/recommendation.py); the LLM writes the
narrative about it. This split matters more here than anywhere else in the
system, because this is the only agent whose output is a recommendation about
whether to hire a person.

Consequences of that split:
  - A score is a HARD prerequisite (unlike Phase 11, where it was optional).
    A hiring recommendation with no evidence base is exactly the thing to
    prevent.
  - If the LLM fails, the recommendation and its arithmetic rationale are
    STILL produced and persisted; only the narrative is missing. Same
    principle as the Matching Agent: the deterministic part survives.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.feedback.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.feedback.schemas import FeedbackNarrative
from app.agents.llm_json_utils import call_llm_for_json
from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.entities.resume import ResumeStatus
from app.domain.feedback.recommendation import ADVISORY_NOTICE, derive_recommendation
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.feedback_repository import FeedbackRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository

MAX_LLM_ATTEMPTS = 2


class FeedbackError(Exception):
    """Raised when feedback generation cannot proceed at all."""


class FeedbackAgent(BaseAgent):
    agent_name = "feedback"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        feedback_repository: FeedbackRepository,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository
        self._jobs = job_repository
        self._scores = score_repository
        self._feedback = feedback_repository
        self._llm = llm_provider

    async def generate(self, resume_id: uuid.UUID):
        """Public entrypoint — wraps `run()` with the resume's audit input_ref."""
        return await self.run(input_ref=f"resume:{resume_id}", resume_id=resume_id)

    async def _execute(self, resume_id: uuid.UUID) -> tuple[dict[str, Any], str]:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise FeedbackError(f"Resume {resume_id} not found")
        if resume.status != ResumeStatus.PARSED:
            raise FeedbackError(
                f"Resume {resume_id} must be parsed before feedback can be generated "
                f"(current status: {resume.status.value})"
            )

        # Hard prerequisite, unlike the Interview Question Agent: the
        # recommendation is derived from this score, so without it there is
        # no defensible basis for a recommendation at all.
        score = await self._scores.get_by_resume_id(resume_id)
        if score is None:
            raise FeedbackError(
                f"Resume {resume_id} has no match score. Run POST /resumes/{resume_id}/match "
                "first — a hiring recommendation requires a computed evidence base."
            )

        job = await self._jobs.get_by_id(resume.job_id)
        if job is None:
            raise FeedbackError(f"Job {resume.job_id} not found")

        # Missing REQUIRED skills specifically (not preferred) gate the top
        # recommendation category.
        required_lower = {s.lower() for s in job.required_skills}
        missing_required = [s for s in score.missing_skills if s.lower() in required_lower]

        recommendation = derive_recommendation(score.similarity_score, missing_required)

        skill_details = await self._resume_skills.list_by_resume(resume_id)
        parsed = resume.parsed_data or {}
        narrative = await self._call_llm(
            job_title=job.title,
            required_skills=job.required_skills,
            preferred_skills=job.preferred_skills,
            candidate_skills=[s.name for s in skill_details],
            missing_skills=score.missing_skills,
            projects=parsed.get("projects") or [],
            experience=parsed.get("experience") or [],
            education=parsed.get("education") or [],
            similarity_score=score.similarity_score,
            recommendation=recommendation.category.value,
            threshold_rationale=recommendation.threshold_rationale,
        )
        narrative_failed = narrative is None

        feedback = CandidateFeedback(
            id=uuid.uuid4(),
            resume_id=resume_id,
            job_id=job.id,
            recommendation=recommendation.category,
            threshold_rationale=recommendation.threshold_rationale,
            summary=narrative.summary if narrative else None,
            strengths=narrative.strengths if narrative else [],
            weaknesses=narrative.weaknesses if narrative else [],
            risk_factors=narrative.risk_factors if narrative else [],
            improvement_suggestions=narrative.improvement_suggestions if narrative else [],
            narrative_generation_failed=narrative_failed,
            created_at=datetime.now(timezone.utc),
        )
        saved = await self._feedback.upsert(feedback)

        output = {
            "recommendation": saved.recommendation.value,
            "threshold_rationale": saved.threshold_rationale,
            "similarity_score": score.similarity_score,
            "summary": saved.summary,
            "strengths": saved.strengths,
            "weaknesses": saved.weaknesses,
            "risk_factors": saved.risk_factors,
            "improvement_suggestions": saved.improvement_suggestions,
            "narrative_generation_failed": narrative_failed,
            "advisory_notice": ADVISORY_NOTICE,
        }
        reasoning = (
            f"Derived recommendation '{saved.recommendation.value}' for resume {resume_id} "
            f"against job '{job.title}'. {saved.threshold_rationale}"
        )
        if narrative_failed:
            reasoning += (
                f" LLM narrative generation failed after {MAX_LLM_ATTEMPTS} attempts; the "
                "recommendation is unaffected since it is derived arithmetically, but the "
                "summary and supporting detail are empty."
            )
        return output, reasoning

    async def _call_llm(self, **kwargs) -> FeedbackNarrative | None:
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(**kwargs),
            validate=FeedbackNarrative.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
