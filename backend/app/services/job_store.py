"""
Background job tracking.

THE PROBLEM THIS SOLVES
-----------------------
Screening a job runs every resume through six agents sequentially. Fifty
resumes is roughly 300 LLM calls, which is minutes to tens of minutes. The
synchronous endpoint holds the HTTP connection open for that entire time,
so any proxy, load balancer, or browser with a sane timeout severs it —
and the work continues server-side with nobody receiving the result.

SCOPE — WHAT THIS IS AND ISN'T
-------------------------------
This uses FastAPI BackgroundTasks with a Redis-backed status store. It
genuinely fixes the timeout problem: the request returns immediately with
a job id, and the client polls for progress.

It does NOT give you:
  - durability across a restart (an in-flight job is lost if the pod dies)
  - distributed execution (work runs in the same process that accepted it)
  - retry of a failed job
  - a queue with backpressure

Those need a real task queue — Celery, ARQ, or Dramatiq with a worker
pool. That's a genuine architectural addition, and half-implementing one
here would be worse than being clear about the boundary. For this scale
(a recruiter screening tens of resumes) BackgroundTasks is the right size;
past that, the upgrade path is to swap this store's implementation for a
queue without changing the API contract.
"""
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as redis

from app.core.observability.logging_config import get_logger

logger = get_logger(__name__)

# Long enough to survive a slow job plus the client polling afterwards,
# short enough that abandoned records expire on their own.
JOB_TTL_SECONDS = 24 * 3600


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BackgroundJob:
    id: str
    kind: str
    status: JobStatus
    created_at: str
    # Progress is reported as "N of M" rather than a percentage: a
    # percentage implies a smoothness this workload doesn't have, since
    # resumes take wildly different times.
    total: int = 0
    completed: int = 0
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    updated_at: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class JobStore:
    """Redis-backed job status.

    Redis rather than in-memory because Gunicorn runs several workers: a
    job started by worker 1 must be pollable through worker 3, and an
    in-process dict would return 404 two times out of three.

    Unlike the rate limiter, this does NOT fail open — if Redis is
    unavailable, a caller must learn that their job status is unknown
    rather than be told the job doesn't exist.
    """

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: redis.Redis | None = None

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)
        return self._client

    @staticmethod
    def _key(job_id: str) -> str:
        return f"job:{job_id}"

    async def create(self, kind: str, total: int = 0) -> BackgroundJob:
        now = datetime.now(timezone.utc).isoformat()
        job = BackgroundJob(
            id=uuid.uuid4().hex,
            kind=kind,
            status=JobStatus.PENDING,
            created_at=now,
            updated_at=now,
            total=total,
        )
        await self._save(job)
        return job

    async def _save(self, job: BackgroundJob) -> None:
        job.updated_at = datetime.now(timezone.utc).isoformat()
        client = await self._get_client()
        await client.set(self._key(job.id), json.dumps(job.to_dict()), ex=JOB_TTL_SECONDS)

    async def get(self, job_id: str) -> BackgroundJob | None:
        client = await self._get_client()
        raw = await client.get(self._key(job_id))
        if raw is None:
            return None
        data = json.loads(raw)
        data["status"] = JobStatus(data["status"])
        return BackgroundJob(**data)

    async def update(
        self,
        job_id: str,
        *,
        status: JobStatus | None = None,
        completed: int | None = None,
        message: str | None = None,
        result: dict | None = None,
        error: str | None = None,
    ) -> None:
        job = await self.get(job_id)
        if job is None:
            # The job's TTL expired mid-run, or Redis was flushed. Log it
            # rather than raising: losing the status record shouldn't abort
            # work that is otherwise progressing fine.
            logger.warning("job record missing during update", extra={"job_id": job_id})
            return
        if status is not None:
            job.status = status
        if completed is not None:
            job.completed = completed
        if message is not None:
            job.message = message
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        await self._save(job)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
