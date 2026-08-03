"""
Skill Extraction Agent.

Pipeline step 2 (per the Phase 1 LangGraph flow): Resume Parsing Agent ->
Skill Extraction Agent -> Job Description Agent -> ...

Given a resume_id (already PARSED by the Resume Parsing Agent), this agent:
1. Reads the raw skill strings from resume.parsed_data["skills"]
2. Resolves each via the curated dictionary (instant, free, deterministic)
3. Batches everything the dictionary couldn't resolve into ONE LLM call
   (not one call per skill) as a fallback
4. Links each resolved skill to the resume via the resume_skills table,
   creating canonical Skill rows as needed

Partial-success model: if the LLM fallback batch fails entirely, dictionary
hits are still persisted — one bad LLM response doesn't discard already-
resolved skills. This differs deliberately from the Resume Parsing Agent,
where a failed parse leaves nothing usable; here, a "mostly resolved" skill
list is still a successful, useful outcome.
"""
import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.agents.llm_json_utils import call_llm_for_json
from app.agents.skill_extractor.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.skill_extractor.schemas import SkillCategorizationOutput
from app.domain.entities.resume import ResumeStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.skill_repository import SkillRepository
from app.domain.skills.normalizer import ResolvedSkill, resolve_from_dictionary

MAX_LLM_ATTEMPTS = 2
# Fixed confidence for LLM-resolved skills, deliberately lower than the
# dictionary's 1.0. Not derived from the LLM's own self-reported confidence
# — LLMs are poorly calibrated at self-assessment, so a fixed constant
# reflecting "AI-inferred, not dictionary-verified" is more honest than a
# number the model made up.
LLM_RESOLVED_CONFIDENCE = 0.7


class SkillExtractionError(Exception):
    """Raised when skill extraction cannot proceed at all (e.g. resume not parsed)."""


class SkillExtractionAgent(BaseAgent):
    agent_name = "skill_extractor"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        resume_repository: ResumeRepository,
        skill_repository: SkillRepository,
        resume_skill_repository: ResumeSkillRepository,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._resumes = resume_repository
        self._skills = skill_repository
        self._resume_skills = resume_skill_repository
        self._llm = llm_provider

    async def extract(self, resume_id: uuid.UUID):
        """Public entrypoint — wraps `run()` with the resume's audit input_ref."""
        return await self.run(input_ref=f"resume:{resume_id}", resume_id=resume_id)

    async def _execute(self, resume_id: uuid.UUID) -> tuple[dict[str, Any], str]:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise SkillExtractionError(f"Resume {resume_id} not found")
        if resume.status != ResumeStatus.PARSED:
            raise SkillExtractionError(
                f"Resume {resume_id} must be parsed before skill extraction can run "
                f"(current status: {resume.status.value})"
            )

        raw_skills: list[str] = (resume.parsed_data or {}).get("skills", [])
        if not raw_skills:
            return (
                {"resolved_skills": [], "unresolved_raw_skills": []},
                "No skills found in parsed resume data — nothing to extract.",
            )

        resolved: list[ResolvedSkill] = []
        unresolved_raw: list[str] = []
        for raw in raw_skills:
            hit = resolve_from_dictionary(raw)
            if hit is not None:
                resolved.append(hit)
            else:
                unresolved_raw.append(raw)

        llm_resolved_count = 0
        llm_failed = False
        if unresolved_raw:
            llm_output = await self._resolve_via_llm(unresolved_raw)
            if llm_output is not None:
                for item in llm_output.skills:
                    resolved.append(
                        ResolvedSkill(
                            raw=item.raw,
                            canonical_name=item.canonical_name,
                            category=item.category,
                            confidence=LLM_RESOLVED_CONFIDENCE,
                        )
                    )
                llm_resolved_count = len(llm_output.skills)
                unresolved_raw = []  # all handled (or the LLM's best guess, per its own instructions)
            else:
                llm_failed = True

        for item in resolved:
            skill = await self._skills.get_or_create(item.canonical_name, item.category)
            await self._resume_skills.upsert(resume_id, skill.id, item.confidence)

        dictionary_count = len(resolved) - llm_resolved_count
        output = {
            "resolved_skills": [
                {
                    "raw": r.raw,
                    "canonical_name": r.canonical_name,
                    "category": r.category.value,
                    "confidence": r.confidence,
                }
                for r in resolved
            ],
            "unresolved_raw_skills": unresolved_raw,
        }
        reasoning = (
            f"Resolved {len(resolved)} of {len(raw_skills)} skills "
            f"({dictionary_count} via dictionary, {llm_resolved_count} via LLM fallback)."
        )
        if llm_failed:
            reasoning += (
                f" LLM fallback failed for {len(unresolved_raw)} skill(s) after "
                f"{MAX_LLM_ATTEMPTS} attempts; those were left unresolved rather than "
                "discarding the dictionary-resolved skills."
            )
        return output, reasoning

    async def _resolve_via_llm(self, raw_skills: list[str]) -> SkillCategorizationOutput | None:
        user_prompt = build_user_prompt(raw_skills)
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            validate=SkillCategorizationOutput.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
