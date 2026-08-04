"""
Retrieval-Augmented Generation over the resume corpus.

Answers recruiter questions that require synthesizing across several
resumes — "which candidates have production Kubernetes experience, and what
did they do with it?" — which semantic search alone can't do, since search
returns documents rather than answers.

DESIGN: groundedness is enforced in code, not requested in a prompt.
Retrieved sources are numbered, the model is required to cite them, and
every citation is then verified against the sources that actually exist.
Claims citing fabricated sources are stripped. The full source text is
returned so any surviving claim can be checked by a human.

SCOPE: this answers questions ABOUT candidates. It does not score, rank, or
recommend — those stay deterministic in Phases 9, 10, and 12.
"""
import uuid
from dataclasses import dataclass, field

from app.agents.llm_json_utils import call_llm_for_json
from app.agents.rag.prompts import SYSTEM_PROMPT, build_retry_prompt, build_user_prompt
from app.agents.rag.schemas import GroundedAnswer
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.rag.citation_validator import ValidatedClaim, validate_claims
from app.domain.rag.context_builder import SourceChunk, build_source_chunks, format_context
from app.domain.search.text_builder import build_resume_text
from app.services.indexing_service import IndexingService

MAX_LLM_ATTEMPTS = 2
DEFAULT_TOP_K = 5
MAX_TOP_K = 20


class RAGError(Exception):
    """Raised when a question cannot be answered at all."""


@dataclass
class RAGAnswer:
    question: str
    answer: str
    claims: list[ValidatedClaim] = field(default_factory=list)
    sources: list[SourceChunk] = field(default_factory=list)
    insufficient_evidence: bool = False
    citation_warnings: list[str] = field(default_factory=list)
    answer_rejected: bool = False


class RAGService:
    def __init__(
        self,
        indexing_service: IndexingService,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        candidate_repository: CandidateRepository,
        llm_provider: LLMProvider,
    ) -> None:
        self._indexing = indexing_service
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository
        self._candidates = candidate_repository
        self._llm = llm_provider

    async def ask(
        self, question: str, top_k: int = DEFAULT_TOP_K, job_id: uuid.UUID | None = None
    ) -> RAGAnswer:
        if not question.strip():
            raise RAGError("Question cannot be empty")
        if not 1 <= top_k <= MAX_TOP_K:
            raise RAGError(f"top_k must be between 1 and {MAX_TOP_K} (got {top_k})")

        # --- 1. Retrieve ---
        hits = await self._indexing.search_resumes(query=question, limit=top_k, job_id=job_id)
        if not hits:
            return RAGAnswer(
                question=question,
                answer=(
                    "No indexed resumes matched this question. Index resumes via "
                    "POST /api/v1/resumes/{resume_id}/index before asking questions about them."
                ),
                insufficient_evidence=True,
            )

        # --- 2. Build numbered context ---
        retrieved = await self._hydrate_hits(hits)
        chunks = build_source_chunks(retrieved)
        if not chunks:
            return RAGAnswer(
                question=question,
                answer="Matching resumes were found but contained no readable content to answer from.",
                insufficient_evidence=True,
            )

        # --- 3. Generate ---
        generated = await self._generate(question, format_context(chunks))
        if generated is None:
            raise RAGError(
                f"The model did not return a valid answer after {MAX_LLM_ATTEMPTS} attempts"
            )

        # --- 4. Validate citations ---
        valid_ids = {chunk.source_id for chunk in chunks}
        validation = validate_claims(
            [{"text": c.text, "source_ids": c.source_ids} for c in generated.claims], valid_ids
        )

        # If every claim failed validation, the answer prose is almost
        # certainly fabricated too. Returning it stripped of claims would
        # still read as authoritative, so the whole answer is rejected.
        if validation.all_claims_ungrounded:
            return RAGAnswer(
                question=question,
                answer=(
                    "An answer was generated but none of its claims could be verified against "
                    "the retrieved resumes, so it has been withheld. The retrieved sources are "
                    "included below for manual review."
                ),
                claims=[],
                sources=chunks,
                insufficient_evidence=True,
                citation_warnings=validation.warnings,
                answer_rejected=True,
            )

        return RAGAnswer(
            question=question,
            answer=generated.answer,
            claims=validation.grounded_claims,
            sources=chunks,
            insufficient_evidence=generated.insufficient_evidence,
            citation_warnings=validation.warnings,
        )

    async def _hydrate_hits(self, hits) -> list[dict]:
        """Turn vector hits into the text and names the context needs.

        Rebuilds resume text from the database rather than storing it in the
        vector payload — the database is the source of truth, and duplicating
        text into the index would let the two drift after a re-parse.
        """
        retrieved: list[dict] = []
        for hit in hits:
            resume = await self._resumes.get_by_id(hit.entity_id)
            if resume is None:
                continue
            skill_details = await self._resume_skills.list_by_resume(hit.entity_id)
            text = build_resume_text(resume, [s.name for s in skill_details])

            candidate_name = "Unidentified candidate"
            if resume.candidate_id:
                candidate = await self._candidates.get_by_id(resume.candidate_id)
                if candidate:
                    candidate_name = candidate.full_name

            retrieved.append(
                {
                    "resume_id": str(hit.entity_id),
                    "candidate_name": candidate_name,
                    "similarity": hit.score,
                    "text": text,
                }
            )
        return retrieved

    async def _generate(self, question: str, context: str) -> GroundedAnswer | None:
        return await call_llm_for_json(
            llm=self._llm,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(question, context),
            validate=GroundedAnswer.model_validate,
            build_retry_prompt=build_retry_prompt,
            max_attempts=MAX_LLM_ATTEMPTS,
        )
