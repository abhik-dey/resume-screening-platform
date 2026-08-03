"""
Interview Question Agent.

Pipeline step 6 (per the Phase 1 LangGraph flow): Ranking Agent ->
Interview Question Agent -> Feedback Agent -> ...

Unlike the Matching and Ranking Agents, this one is IRREDUCIBLY LLM-DEPENDENT.
Scoring and ranking are arithmetic with deterministic answers; writing a good
interview question is a genuinely creative task with no algorithmic fallback.

That has an honest consequence: if the LLM fails, this agent produces
nothing. It does not fabricate placeholder questions, and it does not
silently persist a partial set. A recruiter seeing "generation failed, try
again" is strictly better served than one handed generic filler they might
mistake for tailored analysis.

Questions are grounded in the candidate's real data — their actual projects,
experience, matched skills, and the specific gaps the Matching Agent found.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.interview_question.prompts import (
    SYSTEM_PROMPT,
    build_retry_prompt,
    build_user_prompt,
)
from app.agents.interview_question.schemas import InterviewQuestionSet
from app.agents.llm_json_utils import call_llm_for_json
from app.domain.entities.interview_question import InterviewQuestion
from app.domain.entities.resume import ResumeStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.interview_question_repository import InterviewQuestionRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository

MAX_LLM_ATTEMPTS = 2
DEFAULT_QUESTION_COUNT = 9
MIN_QUESTION_COUNT = 1
MAX_QUESTION_COUNT = 30


class InterviewQuestionError(Exception):
    """Raised when question generation cannot be completed."""


class InterviewQuestionAgent(BaseAgent):
    agent_name = "interview_question"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        job_repository: JobRepository,
        score_repository: ScoreRepository,
        interview_question_repository: InterviewQuestionRepository,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository
        self._jobs = job_repository
        self._scores = score_repository
        self._questions = interview_question_repository
        self._llm = llm_provider

    async def generate(self, resume_id: uuid.UUID, question_count: int = DEFAULT_QUESTION_COUNT):
        """Public entrypoint — wraps `run()` with the resume's audit input_ref."""
        return await self.run(
            input_ref=f"resume:{resume_id}", resume_id=resume_id, question_count=question_count
        )

    async def _execute(self, resume_id: uuid.UUID, question_count: int) -> tuple[dict[str, Any], str]:
        if not MIN_QUESTION_COUNT <= question_count <= MAX_QUESTION_COUNT:
            raise InterviewQuestionError(
                f"question_count must be between {MIN_QUESTION_COUNT} and {MAX_QUESTION_COUNT} "
                f"(got {question_count})"
            )

        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise InterviewQuestionError(f"Resume {resume_id} not found")
        if resume.status != ResumeStatus.PARSED:
            raise InterviewQuestionError(
                f"Resume {resume_id} must be parsed before questions can be generated "
                f"(current status: {resume.status.value})"
            )

        job = await self._jobs.get_by_id(resume.job_id)
        if job is None:
            raise InterviewQuestionError(f"Job {resume.job_id} not found")

        skill_details = await self._resume_skills.list_by_resume(resume_id)
        candidate_skills = [s.name for s in skill_details]

        # The score is optional input, not a prerequisite: questions are more
        # targeted when gaps are known, but a recruiter shouldn't be blocked
        # from generating questions just because matching hasn't run yet.
        score = await self._scores.get_by_resume_id(resume_id)
        missing_skills = score.missing_skills if score else []

        parsed = resume.parsed_data or {}
        generated = await self._call_llm(
            job_title=job.title,
            required_skills=job.required_skills,
            preferred_skills=job.preferred_skills,
            candidate_skills=candidate_skills,
            missing_skills=missing_skills,
            projects=parsed.get("projects") or [],
            experience=parsed.get("experience") or [],
            total_questions=question_count,
        )
        if generated is None or not generated.questions:
            # No deterministic fallback exists for a creative task. Failing
            # cleanly beats persisting fabricated filler.
            raise InterviewQuestionError(
                f"LLM did not return usable questions after {MAX_LLM_ATTEMPTS} attempts; "
                "no questions were saved"
            )

        now = datetime.now(timezone.utc)
        questions = [
            InterviewQuestion(
                id=uuid.uuid4(),
                resume_id=resume_id,
                job_id=job.id,
                question=item.question,
                category=item.category,
                difficulty=item.difficulty,
                rationale=item.rationale,
                created_at=now,
            )
            for item in generated.questions
        ]
        saved = await self._questions.replace_for_resume(resume_id, questions)

        by_category: dict[str, int] = {}
        by_difficulty: dict[str, int] = {}
        for q in saved:
            by_category[q.category.value] = by_category.get(q.category.value, 0) + 1
            by_difficulty[q.difficulty.value] = by_difficulty.get(q.difficulty.value, 0) + 1

        output = {
            "questions": [
                {
                    "id": str(q.id),
                    "question": q.question,
                    "category": q.category.value,
                    "difficulty": q.difficulty.value,
                    "rationale": q.rationale,
                }
                for q in saved
            ],
            "by_category": by_category,
            "by_difficulty": by_difficulty,
            "grounded_in_missing_skills": missing_skills,
        }
        reasoning = (
            f"Generated {len(saved)} interview question(s) for resume {resume_id} against job "
            f"'{job.title}'. Breakdown by category: {by_category}; by difficulty: {by_difficulty}."
        )
        if missing_skills:
            reasoning += f" Grounded gap-probing questions in {len(missing_skills)} missing skill(s)."
        else:
            reasoning += (
                " No match score available, so questions were grounded in the candidate's "
                "skills, projects, and experience only."
                if score is None
                else " Candidate had no missing required skills."
            )
        return output, reasoning

    async def _call_llm(self, **kwargs) -> InterviewQuestionSet | None:
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(**kwargs),
            validate=InterviewQuestionSet.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
