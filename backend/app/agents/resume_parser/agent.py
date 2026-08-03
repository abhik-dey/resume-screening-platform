"""
Resume Parsing Agent.

Pipeline step 1 (per the Phase 1 LangGraph flow): Resume Upload -> Resume
Parsing Agent -> Skill Extraction Agent -> ...

Given a resume_id, this agent:
1. Loads the resume's file bytes from storage
2. Extracts plain text (PDF/DOCX -> text)
3. Asks the configured LLM to extract structured data as JSON, retrying
   once if the response isn't valid JSON matching the schema
4. Resolves or creates the Candidate record by email (this is exactly the
   point where Resume.candidate_id, nullable since Phase 4, gets filled in)
5. Persists the parsed data and updated status back onto the Resume
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.llm_json_utils import call_llm_for_json
from app.agents.resume_parser.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.resume_parser.schemas import ParsedResumeOutput
from app.domain.entities.candidate import Candidate
from app.domain.entities.resume import ResumeStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.infrastructure.text_extraction.extractor import TextExtractionError, extract_text

MAX_LLM_ATTEMPTS = 2


class ResumeParsingError(Exception):
    """Raised when parsing cannot be completed, after all retries are exhausted."""


class ResumeParsingAgent(BaseAgent):
    agent_name = "resume_parser"

    def __init__(
        self,
        audit_log_repository: AuditLogRepository,
        resume_repository: ResumeRepository,
        candidate_repository: CandidateRepository,
        file_storage: FileStorage,
        llm_provider: LLMProvider,
        model_name: str,
    ) -> None:
        super().__init__(audit_log_repository, model_name)
        self._resumes = resume_repository
        self._candidates = candidate_repository
        self._storage = file_storage
        self._llm = llm_provider

    async def parse(self, resume_id: uuid.UUID):
        """Public entrypoint — wraps `run()` with the resume's audit input_ref."""
        return await self.run(input_ref=f"resume:{resume_id}", resume_id=resume_id)

    async def _execute(self, resume_id: uuid.UUID) -> tuple[dict[str, Any], str]:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise ResumeParsingError(f"Resume {resume_id} not found")

        try:
            content = await self._storage.read(resume.storage_path)
            extension = "." + resume.original_filename.rsplit(".", 1)[-1].lower()
            resume_text = extract_text(content, extension)
        except (TextExtractionError, FileNotFoundError) as exc:
            await self._mark_failed(resume_id)
            raise ResumeParsingError(f"Text extraction failed: {exc}") from exc

        parsed = await self._call_llm_with_retry(resume_text)
        if parsed is None:
            await self._mark_failed(resume_id)
            raise ResumeParsingError(
                f"LLM did not return valid structured output after {MAX_LLM_ATTEMPTS} attempts"
            )

        candidate_id = await self._resolve_candidate(parsed)

        resume.raw_text = resume_text
        resume.parsed_data = parsed.model_dump(mode="json")
        resume.status = ResumeStatus.PARSED
        resume.candidate_id = candidate_id
        await self._resumes.update(resume)

        reasoning = (
            f"Extracted {len(parsed.education)} education entries, "
            f"{len(parsed.experience)} experience entries, {len(parsed.skills)} skills. "
            + (
                f"Resolved candidate {candidate_id}."
                if candidate_id
                else "No email found in resume — candidate not resolved."
            )
        )
        return resume.parsed_data, reasoning

    async def _call_llm_with_retry(self, resume_text: str) -> ParsedResumeOutput | None:
        user_prompt = build_user_prompt(resume_text)
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            validate=ParsedResumeOutput.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )

    async def _resolve_candidate(self, parsed: ParsedResumeOutput) -> uuid.UUID | None:
        if not parsed.email:
            return None

        existing = await self._candidates.get_by_email(parsed.email)
        if existing is not None:
            return existing.id

        candidate = Candidate(
            id=uuid.uuid4(),
            full_name=parsed.full_name or "Unknown",
            email=parsed.email,
            phone=parsed.phone,
            links=parsed.links,
            created_at=datetime.now(timezone.utc),
        )
        created = await self._candidates.create(candidate)
        return created.id

    async def _mark_failed(self, resume_id: uuid.UUID) -> None:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is not None:
            resume.status = ResumeStatus.FAILED
            await self._resumes.update(resume)
