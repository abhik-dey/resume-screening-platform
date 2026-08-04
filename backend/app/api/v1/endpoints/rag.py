"""RAG question-answering endpoint."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_rag_service
from app.api.v1.schemas.rag import AskRequest, AskResponse, ClaimResponse, SourceResponse
from app.domain.entities.user import User
from app.services.rag_service import RAGError, RAGService

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


@router.post("/ask", response_model=AskResponse)
async def ask(
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    rag: RAGService = Depends(get_rag_service),
) -> AskResponse:
    """Ask a question answered from indexed resumes.

    Useful for questions requiring synthesis across candidates — "who has
    production Kubernetes experience and what did they build with it?" —
    which plain semantic search can't answer, since search returns
    documents rather than answers.

    Every claim is cited and every citation is verified against the
    retrieved sources; claims citing sources that don't exist are stripped
    and reported in `citation_warnings`. The full source text is returned
    so any claim can be checked independently.

    This does not score, rank, or recommend candidates — those remain
    deterministic and are handled elsewhere.
    """
    job_uuid = None
    if payload.job_id:
        try:
            job_uuid = UUID(payload.job_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="job_id must be a valid UUID"
            ) from exc

    try:
        result = await rag.ask(
            question=payload.question, top_k=payload.top_k, job_id=job_uuid
        )
    except RAGError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AskResponse(
        question=result.question,
        answer=result.answer,
        claims=[
            ClaimResponse(text=c.text, source_ids=c.source_ids, warning=c.warning)
            for c in result.claims
        ],
        sources=[
            SourceResponse(
                source_id=s.source_id,
                resume_id=s.resume_id,
                candidate_name=s.candidate_name,
                similarity=round(s.similarity, 4),
                text=s.text,
            )
            for s in result.sources
        ],
        insufficient_evidence=result.insufficient_evidence,
        citation_warnings=result.citation_warnings,
        answer_rejected=result.answer_rejected,
    )
