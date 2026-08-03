"""
Ranking Agent.

Pipeline step 5 (per the Phase 1 LangGraph flow): Matching Agent ->
Ranking Agent -> Interview Question Agent -> ...

NO LLM DEPENDENCY. Ranking is sorting a list of numbers with defined
tie-breaks — pure arithmetic. Adding an LLM would introduce latency, cost,
and non-determinism to a problem that has none of those, so this agent
deliberately has no LLMProvider at all. It still extends BaseAgent because
audit logging applies regardless of whether an LLM was involved: the
question "why is this candidate ranked #3?" deserves an answer either way.

Given a job_id, this agent:
1. Loads every score for that job (from the Matching Agent)
2. Optionally re-scores them with recruiter-supplied weights
3. Orders them deterministically and assigns competition ranks
4. Persists each rank

Unlike the per-resume agents, this one operates on a JOB — ranking is
inherently comparative and meaningless for a single candidate in isolation.
"""
import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.domain.entities.resume import ResumeStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from app.domain.matching.ranker import build_ranking_summary, rank_scores
from app.domain.matching.resume_facts import estimate_years_experience, extract_education_text
from app.domain.matching.scorer import ScoringWeights, compute_match_score


class RankingError(Exception):
    """Raised when ranking cannot proceed at all."""


class RankingAgent(BaseAgent):
    agent_name = "ranking"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        model_name: str = "none (deterministic)",
    ) -> None:
        # model_name records "no LLM was used" in the audit trail rather
        # than leaving it blank or falsely naming a model.
        super().__init__(audit_log_repository, model_name)
        self._jobs = job_repository
        self._scores = score_repository
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository

    async def rank(self, job_id: uuid.UUID, weights: ScoringWeights | None = None):
        """Public entrypoint — wraps `run()` with the job's audit input_ref."""
        return await self.run(input_ref=f"job:{job_id}", job_id=job_id, weights=weights)

    async def _execute(
        self, job_id: uuid.UUID, weights: ScoringWeights | None
    ) -> tuple[dict[str, Any], str]:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise RankingError(f"Job {job_id} not found")

        scores = await self._scores.list_by_job(job_id)
        if not scores:
            return (
                {"total_candidates": 0, "ordering": [], "weights_applied": None},
                "No scored candidates for this job yet — run matching on its resumes first.",
            )

        rescored_count = 0
        if weights is not None:
            scores, rescored_count = await self._rescore_with_weights(scores, job, weights)

        ranked = rank_scores(scores)
        for item in ranked:
            await self._scores.update_rank(item.score.id, item.rank)

        summary = build_ranking_summary(ranked)
        summary["weights_applied"] = (
            {
                "skills": weights.skills,
                "experience": weights.experience,
                "education": weights.education,
            }
            if weights
            else None
        )

        tie_count = sum(1 for item in ranked if item.tie_break_reason is not None)
        reasoning = f"Ranked {len(ranked)} candidate(s) for job '{job.title}'."
        if weights is not None:
            reasoning += (
                f" Re-scored {rescored_count} candidate(s) using custom weights "
                f"(skills={weights.skills}, experience={weights.experience}, "
                f"education={weights.education})."
            )
        if tie_count:
            reasoning += (
                f" {tie_count} candidate(s) tied on merit and share a rank; "
                "ordering within ties is by resume ID for determinism."
            )
        return summary, reasoning

    async def _rescore_with_weights(self, scores, job, weights: ScoringWeights):
        """Recompute similarity scores using recruiter-supplied weights.

        Reuses the exact same scorer as the Matching Agent (Phase 9) rather
        than reimplementing scoring — one algorithm, parameterized.
        """
        updated = []
        rescored = 0
        for score in scores:
            resume = await self._resumes.get_by_id(score.resume_id)
            if resume is None or resume.status != ResumeStatus.PARSED:
                # Keep the existing score rather than dropping the candidate
                # from the ranking entirely.
                updated.append(score)
                continue

            skill_details = await self._resume_skills.list_by_resume(score.resume_id)
            result = compute_match_score(
                candidate_skills=[s.name for s in skill_details],
                required_skills=job.required_skills,
                preferred_skills=job.preferred_skills,
                candidate_years_experience=estimate_years_experience(resume.parsed_data),
                required_years_experience=job.min_experience_years,
                candidate_education=extract_education_text(resume.parsed_data),
                required_education=job.education_requirement,
                weights=weights,
            )
            score.similarity_score = result.overall_score
            score.skill_overlap = result.skill_overlap
            score.missing_skills = result.missing_skills
            updated.append(score)
            rescored += 1
        return updated, rescored
