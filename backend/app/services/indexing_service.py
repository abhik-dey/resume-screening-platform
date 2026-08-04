"""
Semantic indexing and search.

SCOPE NOTE — this is deliberately SEPARATE from Phase 9 matching.

It would be easy to blend cosine similarity into the match score, and
tempting: it looks like a richer signal. But the Phase 9 score was built to
be deterministic, arithmetic, and explainable to a candidate or auditor.
Mixing in an embedding similarity would destroy all three properties for a
gain that isn't clearly real.

So embeddings serve DISCOVERY (find candidates resembling this description)
while the deterministic score serves EVALUATION (how well does this
candidate meet the stated requirements). Different jobs, kept apart.
"""
import uuid

from app.domain.entities.resume import ResumeStatus
from app.domain.interfaces.embedding_provider import EmbeddingProvider
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.vector_store import VectorSearchResult, VectorStore
from app.domain.search.text_builder import build_job_text, build_resume_text

RESUME_COLLECTION = "resumes"
JOB_COLLECTION = "jobs"


class IndexingError(Exception):
    """Raised when indexing cannot proceed."""


class IndexingService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        resume_repository: ResumeRepository,
        resume_skill_repository: ResumeSkillRepository,
        job_repository: JobRepository,
    ) -> None:
        self._embeddings = embedding_provider
        self._store = vector_store
        self._resumes = resume_repository
        self._resume_skills = resume_skill_repository
        self._jobs = job_repository

    async def ensure_collections(self) -> None:
        """Idempotent — safe to call on every startup."""
        for collection in (RESUME_COLLECTION, JOB_COLLECTION):
            await self._store.ensure_collection(collection, self._embeddings.dimensions)

    async def index_resume(self, resume_id: uuid.UUID) -> dict:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise IndexingError(f"Resume {resume_id} not found")
        if resume.status != ResumeStatus.PARSED:
            raise IndexingError(
                f"Resume {resume_id} must be parsed before indexing "
                f"(current status: {resume.status.value})"
            )

        skill_details = await self._resume_skills.list_by_resume(resume_id)
        text = build_resume_text(resume, [s.name for s in skill_details])
        if not text.strip():
            raise IndexingError(
                f"Resume {resume_id} produced no indexable text — it may have parsed "
                "without extracting skills, experience, or projects"
            )

        await self.ensure_collections()
        vectors = await self._embeddings.embed([text])
        await self._store.upsert(
            collection=RESUME_COLLECTION,
            entity_id=resume_id,
            vector=vectors[0],
            payload={
                "resume_id": str(resume_id),
                "job_id": str(resume.job_id),
                # Recorded so it's later possible to tell which model produced
                # a vector — vectors from different models aren't comparable.
                "embedding_model": self._embeddings.model_name,
            },
        )
        return {
            "resume_id": str(resume_id),
            "text_length": len(text),
            "dimensions": self._embeddings.dimensions,
            "embedding_model": self._embeddings.model_name,
        }

    async def index_job(self, job_id: uuid.UUID) -> dict:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise IndexingError(f"Job {job_id} not found")

        text = build_job_text(job)
        await self.ensure_collections()
        vectors = await self._embeddings.embed([text])
        await self._store.upsert(
            collection=JOB_COLLECTION,
            entity_id=job_id,
            vector=vectors[0],
            payload={"job_id": str(job_id), "embedding_model": self._embeddings.model_name},
        )
        return {
            "job_id": str(job_id),
            "text_length": len(text),
            "dimensions": self._embeddings.dimensions,
            "embedding_model": self._embeddings.model_name,
        }

    async def search_resumes(
        self, query: str, limit: int = 10, job_id: uuid.UUID | None = None
    ) -> list[VectorSearchResult]:
        """Free-text semantic search across indexed resumes.

        `job_id` restricts results to one job's applicants — the filtered-
        search capability that motivated choosing Qdrant in Phase 1.
        """
        if not query.strip():
            raise IndexingError("Search query cannot be empty")

        await self.ensure_collections()
        vectors = await self._embeddings.embed([query])
        filters = {"job_id": str(job_id)} if job_id else None
        return await self._store.search(
            collection=RESUME_COLLECTION, vector=vectors[0], limit=limit, filters=filters
        )

    async def find_similar_candidates(
        self, job_id: uuid.UUID, limit: int = 10, restrict_to_job: bool = True
    ) -> list[VectorSearchResult]:
        """Find resumes semantically closest to a job's description.

        By default this searches only that job's own applicants. Setting
        `restrict_to_job=False` searches every indexed resume — useful for
        surfacing strong candidates who applied to a *different* role, which
        keyword search would never reveal.
        """
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise IndexingError(f"Job {job_id} not found")

        await self.ensure_collections()
        vectors = await self._embeddings.embed([build_job_text(job)])
        filters = {"job_id": str(job_id)} if restrict_to_job else None
        return await self._store.search(
            collection=RESUME_COLLECTION, vector=vectors[0], limit=limit, filters=filters
        )

    async def delete_resume_index(self, resume_id: uuid.UUID) -> None:
        await self._store.delete(RESUME_COLLECTION, resume_id)
