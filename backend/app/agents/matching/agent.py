"""
Matching Agent.

Pipeline step 4 (per the Phase 1 LangGraph flow): Job Description Agent ->
Matching Agent -> Ranking Agent -> ...

Given a resume_id, this agent:
1. Loads the resume's canonical skills (from the Skill Extraction Agent)
   and the job's requirements (from the Job Description Agent)
2. Computes a DETERMINISTIC score via domain/matching/scorer.py — no LLM
3. Optionally enriches it with LLM-generated strengths/weaknesses prose
4. Persists a Score row (upsert, 1:1 with the resume)

The separation in step 2/3 is the point of this agent's design: the number
is arithmetic and reproducible; the prose is judgment and can fail without
invalidating the number. If the LLM call fails, the score still persists
and the run is still a success.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.llm_json_utils import call_llm_for_json
from app.agents.matching.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.matching.schemas import QualitativeAnalysis
from app.domain.entities.resume import ResumeStatus
from app.domain.entities.score import Score
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from app.domain.matching.resume_facts import estimate_years_experience, extract_education_text
from app.domain.matching.scorer import MatchResult, compute_match_score

MAX_LLM_ATTEMPTS = 2


class MatchingError(Exception):
    """Raised when matching cannot proceed at all."""


def _build_explanation(result: MatchResult) -> str:
    """Human-readable explanation derived from the actual computed numbers —
    never from the LLM, so it can't drift from the score it describes."""
    lines = [f"Overall match score: {result.overall_score:.2f} (0.00-1.00)."]
    for component in result.components:
        lines.append(
            f"- {component.name.capitalize()}: {component.raw_score:.2f} x weight "
            f"{component.weight:.2f} = {component.weighted_score:.3f}. {component.detail}"
        )
    if result.missing_required:
        lines.append(f"Missing required skills: {', '.join(result.missing_required)}.")
    return "\n".join(lines)


class MatchingAgent(BaseAgent):
    agent_name = "matching"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository
        self._jobs = job_repository
        self._scores = score_repository
        self._llm = llm_provider

    async def match(self, resume_id: uuid.UUID):
        """Public entrypoint — wraps `run()` with the resume's audit input_ref."""
        return await self.run(input_ref=f"resume:{resume_id}", resume_id=resume_id)

    async def _execute(self, resume_id: uuid.UUID) -> tuple[dict[str, Any], str]:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise MatchingError(f"Resume {resume_id} not found")
        if resume.status != ResumeStatus.PARSED:
            raise MatchingError(
                f"Resume {resume_id} must be parsed before matching "
                f"(current status: {resume.status.value})"
            )

        job = await self._jobs.get_by_id(resume.job_id)
        if job is None:
            raise MatchingError(f"Job {resume.job_id} not found")

        skill_details = await self._resume_skills.list_by_resume(resume_id)
        candidate_skills = [s.name for s in skill_details]

        # --- Deterministic scoring: no LLM involved past this point's inputs ---
        result = compute_match_score(
            candidate_skills=candidate_skills,
            required_skills=job.required_skills,
            preferred_skills=job.preferred_skills,
            candidate_years_experience=estimate_years_experience(resume.parsed_data),
            required_years_experience=job.min_experience_years,
            candidate_education=extract_education_text(resume.parsed_data),
            required_education=job.education_requirement,
        )
        breakdown = result.to_breakdown_dict()
        explanation = _build_explanation(result)

        # --- Optional LLM enrichment: failure here must not lose the score ---
        analysis = await self._analyze_qualitatively(
            candidate_skills, job.title, job.required_skills, job.preferred_skills, breakdown
        )
        llm_failed = analysis is None
        strengths = analysis.strengths if analysis else []
        weaknesses = analysis.weaknesses if analysis else []

        existing = await self._scores.get_by_resume_id(resume_id)
        await self._scores.upsert(
            Score(
                id=existing.id if existing else uuid.uuid4(),
                resume_id=resume_id,
                job_id=job.id,
                similarity_score=result.overall_score,
                skill_overlap=result.skill_overlap,
                missing_skills=result.missing_skills,
                strengths=strengths,
                weaknesses=weaknesses,
                rank=existing.rank if existing else None,
                explanation=explanation,
                created_at=datetime.now(timezone.utc),
            )
        )

        reasoning = (
            f"Computed deterministic match score {result.overall_score:.2f} for resume {resume_id} "
            f"against job '{job.title}'. "
            f"Matched {len(result.matched_required)}/{len(job.required_skills)} required skills."
        )
        if llm_failed:
            reasoning += (
                f" Qualitative LLM analysis failed after {MAX_LLM_ATTEMPTS} attempts; "
                "the score is unaffected since it is computed arithmetically, "
                "but strengths/weaknesses were left empty."
            )

        output = {
            "breakdown": breakdown,
            "explanation": explanation,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "qualitative_analysis_failed": llm_failed,
        }
        return output, reasoning

    async def _analyze_qualitatively(
        self,
        candidate_skills: list[str],
        job_title: str,
        required_skills: list[str],
        preferred_skills: list[str],
        breakdown: dict,
    ) -> QualitativeAnalysis | None:
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(
                candidate_skills, job_title, required_skills, preferred_skills, breakdown
            ),
            validate=QualitativeAnalysis.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
