"""Semantic search and indexing endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_candidate_repository,
    get_current_user,
    get_embedding_provider_dependency,
    get_indexing_service,
    get_resume_repository,
    require_roles,
)
from app.api.v1.schemas.search import IndexResult, SearchHit, SearchRequest, SearchResponse
from app.domain.entities.user import User, UserRole
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.embedding_provider import EmbeddingProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.vector_store import VectorSearchResult
from app.services.indexing_service import IndexingError, IndexingService

router = APIRouter(tags=["search"])


async def _enrich_hits(
    results: list[VectorSearchResult],
    resume_repo: ResumeRepository,
    candidate_repo: CandidateRepository,
) -> list[SearchHit]:
    """Turn bare vector IDs into something a recruiter can act on."""
    hits: list[SearchHit] = []
    for result in results:
        resume = await resume_repo.get_by_id(result.entity_id)
        candidate_name = candidate_email = None
        if resume and resume.candidate_id:
            candidate = await candidate_repo.get_by_id(resume.candidate_id)
            if candidate:
                candidate_name = candidate.full_name
                candidate_email = candidate.email
        hits.append(
            SearchHit(
                resume_id=result.entity_id,
                job_id=resume.job_id if resume else None,
                similarity=round(result.score, 4),
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                original_filename=resume.original_filename if resume else None,
            )
        )
    return hits


@router.post("/api/v1/resumes/{resume_id}/index", response_model=IndexResult)
async def index_resume(
    resume_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    indexing: IndexingService = Depends(get_indexing_service),
) -> IndexResult:
    """Embed and index a parsed resume for semantic search.

    Re-indexing replaces the existing vector rather than duplicating it.
    """
    try:
        result = await indexing.index_resume(resume_id)
    except IndexingError as exc:
        return IndexResult(success=False, reasoning=str(exc))
    return IndexResult(
        success=True,
        reasoning=(
            f"Indexed resume {resume_id} ({result['text_length']} chars, "
            f"{result['dimensions']} dimensions)."
        ),
        dimensions=result["dimensions"],
        embedding_model=result["embedding_model"],
    )


@router.post("/api/v1/jobs/{job_id}/index", response_model=IndexResult)
async def index_job(
    job_id: UUID,
    current_user: User = Depends(require_roles(UserRole.RECRUITER, UserRole.ADMIN)),
    indexing: IndexingService = Depends(get_indexing_service),
) -> IndexResult:
    try:
        result = await indexing.index_job(job_id)
    except IndexingError as exc:
        return IndexResult(success=False, reasoning=str(exc))
    return IndexResult(
        success=True,
        reasoning=f"Indexed job {job_id} ({result['text_length']} chars).",
        dimensions=result["dimensions"],
        embedding_model=result["embedding_model"],
    )


@router.post("/api/v1/search/resumes", response_model=SearchResponse)
async def search_resumes(
    payload: SearchRequest,
    current_user: User = Depends(get_current_user),
    indexing: IndexingService = Depends(get_indexing_service),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider_dependency),
    resume_repo: ResumeRepository = Depends(get_resume_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
) -> SearchResponse:
    """Free-text semantic search across indexed resumes.

    Finds candidates by meaning rather than exact keywords — a query like
    "built fault-tolerant distributed systems" can surface relevant people
    who never used those exact words.

    This is a DISCOVERY tool. It does not affect match scores, which remain
    deterministic and computed separately.
    """
    try:
        results = await indexing.search_resumes(
            query=payload.query, limit=payload.limit, job_id=payload.job_id
        )
    except IndexingError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    hits = await _enrich_hits(results, resume_repo, candidate_repo)
    return SearchResponse(
        query=payload.query,
        embedding_model=embeddings.model_name,
        total_hits=len(hits),
        results=hits,
    )


@router.get("/api/v1/jobs/{job_id}/similar-candidates", response_model=SearchResponse)
async def find_similar_candidates(
    job_id: UUID,
    limit: int = 10,
    restrict_to_job: bool = True,
    current_user: User = Depends(get_current_user),
    indexing: IndexingService = Depends(get_indexing_service),
    embeddings: EmbeddingProvider = Depends(get_embedding_provider_dependency),
    resume_repo: ResumeRepository = Depends(get_resume_repository),
    candidate_repo: CandidateRepository = Depends(get_candidate_repository),
) -> SearchResponse:
    """Find indexed resumes semantically closest to this job's description.

    Set `restrict_to_job=false` to search every indexed resume, surfacing
    strong candidates who applied to a different role — something keyword
    search over one job's applicants could never find.
    """
    try:
        results = await indexing.find_similar_candidates(
            job_id=job_id, limit=limit, restrict_to_job=restrict_to_job
        )
    except IndexingError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    hits = await _enrich_hits(results, resume_repo, candidate_repo)
    return SearchResponse(
        query=f"(job description for {job_id})",
        embedding_model=embeddings.model_name,
        total_hits=len(hits),
        results=hits,
    )
