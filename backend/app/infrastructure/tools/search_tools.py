"""Search tools — resume semantic search and scoped database queries."""
from typing import Any

from app.domain.entities.user import UserRole
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.score_repository import ScoreRepository
from app.domain.tools.base import Tool, ToolError, ToolResult
from app.services.indexing_service import IndexingError, IndexingService


class ResumeSearchTool(Tool):
    name = "resume_search"
    description = (
        "Semantic search over indexed resumes. Finds candidates by meaning rather than "
        "exact keywords. Returns resume IDs, candidate names, and similarity scores."
    )
    required_role = UserRole.VIEWER

    def __init__(
        self,
        indexing_service: IndexingService,
        resume_repository: ResumeRepository,
        candidate_repository: CandidateRepository,
    ) -> None:
        self._indexing = indexing_service
        self._resumes = resume_repository
        self._candidates = candidate_repository

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 1000, "description": "What to search for"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Max results"},
                "job_id": {"type": "string", "description": "Restrict to one job's applicants"},
            },
            "required": ["query"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        import uuid as _uuid

        job_id = None
        if params.get("job_id"):
            try:
                job_id = _uuid.UUID(params["job_id"])
            except ValueError as exc:
                raise ToolError(f"job_id is not a valid UUID: {params['job_id']}") from exc

        try:
            hits = await self._indexing.search_resumes(
                query=params["query"], limit=params.get("limit", 10), job_id=job_id
            )
        except IndexingError as exc:
            raise ToolError(str(exc)) from exc

        results = []
        for hit in hits:
            resume = await self._resumes.get_by_id(hit.entity_id)
            name = None
            if resume and resume.candidate_id:
                candidate = await self._candidates.get_by_id(resume.candidate_id)
                name = candidate.full_name if candidate else None
            results.append(
                {
                    "resume_id": str(hit.entity_id),
                    "candidate_name": name or "Unidentified candidate",
                    "similarity": round(hit.score, 4),
                    "job_id": str(resume.job_id) if resume else None,
                }
            )
        return ToolResult(success=True, data={"query": params["query"], "results": results})


class DatabaseSearchTool(Tool):
    name = "database_search"
    description = (
        "Look up structured records: jobs, candidates, or a job's scored candidates. "
        "Supports a fixed set of scoped queries only."
    )
    required_role = UserRole.VIEWER

    def __init__(
        self,
        job_repository: JobRepository,
        candidate_repository: CandidateRepository,
        resume_repository: ResumeRepository,
        score_repository: ScoreRepository,
    ) -> None:
        self._jobs = job_repository
        self._candidates = candidate_repository
        self._resumes = resume_repository
        self._scores = score_repository

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                # A fixed enum, NOT free-form SQL. An LLM composing SQL against
                # a hiring database is an injection vector with no upside —
                # every genuinely useful query shape is enumerable here.
                "query_type": {
                    "type": "string",
                    "enum": ["list_jobs", "get_job", "find_candidate_by_email", "job_scores"],
                },
                "job_id": {"type": "string"},
                "email": {"type": "string", "maxLength": 255},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["query_type"],
        }

    async def execute(self, params: dict[str, Any]) -> ToolResult:

        query_type = params["query_type"]
        limit = params.get("limit", 20)

        if query_type == "list_jobs":
            jobs = await self._jobs.list_all(skip=0, limit=limit)
            return ToolResult(
                success=True,
                data={
                    "jobs": [
                        {
                            "id": str(j.id),
                            "title": j.title,
                            "status": j.status.value,
                            "required_skills": j.required_skills,
                        }
                        for j in jobs
                    ]
                },
            )

        if query_type == "get_job":
            if not params.get("job_id"):
                raise ToolError("query_type 'get_job' requires 'job_id'")
            job = await self._jobs.get_by_id(_parse_uuid(params["job_id"], "job_id"))
            if job is None:
                raise ToolError(f"Job {params['job_id']} not found")
            return ToolResult(
                success=True,
                data={
                    "id": str(job.id),
                    "title": job.title,
                    "description": job.description,
                    "required_skills": job.required_skills,
                    "preferred_skills": job.preferred_skills,
                    "min_experience_years": job.min_experience_years,
                    "status": job.status.value,
                },
            )

        if query_type == "find_candidate_by_email":
            if not params.get("email"):
                raise ToolError("query_type 'find_candidate_by_email' requires 'email'")
            candidate = await self._candidates.get_by_email(params["email"])
            if candidate is None:
                return ToolResult(
                    success=True, data={"found": False, "email": params["email"]}
                )
            return ToolResult(
                success=True,
                data={
                    "found": True,
                    "id": str(candidate.id),
                    "full_name": candidate.full_name,
                    "email": candidate.email,
                },
            )

        if query_type == "job_scores":
            if not params.get("job_id"):
                raise ToolError("query_type 'job_scores' requires 'job_id'")
            job_uuid = _parse_uuid(params["job_id"], "job_id")
            scores = await self._scores.list_by_job(job_uuid)
            return ToolResult(
                success=True,
                data={
                    "job_id": params["job_id"],
                    "scores": [
                        {
                            "resume_id": str(s.resume_id),
                            "similarity_score": s.similarity_score,
                            "rank": s.rank,
                            "missing_skills": s.missing_skills,
                        }
                        for s in scores[:limit]
                    ],
                },
            )

        raise ToolError(f"Unsupported query_type: {query_type}")


def _parse_uuid(value: str, field: str):
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except ValueError as exc:
        raise ToolError(f"{field} is not a valid UUID: {value}") from exc
