"""
Resume use-case orchestration: upload, retrieval, listing, download.

Depends only on abstract interfaces (JobRepository, ResumeRepository,
FileStorage) — never on SQLAlchemy or the filesystem directly. That's what
lets the entire upload flow, including its validation and rejection paths,
be unit-tested with in-memory fakes.
"""
import uuid
from datetime import datetime, timezone

from app.domain.entities.job import JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.validation.resume_file import validate_resume_file


class JobNotFoundError(Exception):
    def __init__(self, job_id: uuid.UUID) -> None:
        super().__init__(f"Job {job_id} not found")


class JobNotOpenError(Exception):
    def __init__(self, job_id: uuid.UUID, status: JobStatus) -> None:
        super().__init__(f"Job {job_id} is not open for applications (status: {status.value})")


class ResumeNotFoundError(Exception):
    def __init__(self, resume_id: uuid.UUID) -> None:
        super().__init__(f"Resume {resume_id} not found")


class ResumeService:
    def __init__(
        self,
        resume_repository: ResumeRepository,
        job_repository: JobRepository,
        file_storage: FileStorage,
        max_upload_size_bytes: int,
    ) -> None:
        self._resumes = resume_repository
        self._jobs = job_repository
        self._storage = file_storage
        self._max_upload_size_bytes = max_upload_size_bytes

    async def upload(
        self, job_id: uuid.UUID, uploaded_by: uuid.UUID, filename: str, content: bytes
    ) -> Resume:
        job = await self._jobs.get_by_id(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        if job.status != JobStatus.OPEN:
            raise JobNotOpenError(job_id, job.status)

        # Raises a ResumeValidationError subclass on any failure — the API
        # layer maps these to 400 responses with the specific reason.
        validate_resume_file(filename, content, self._max_upload_size_bytes)

        storage_path = await self._storage.save(content, filename)

        resume = Resume(
            id=uuid.uuid4(),
            job_id=job_id,
            uploaded_by=uploaded_by,
            storage_path=storage_path,
            original_filename=filename,
            status=ResumeStatus.UPLOADED,
            created_at=datetime.now(timezone.utc),
        )
        return await self._resumes.create(resume)

    async def get_resume(self, resume_id: uuid.UUID) -> Resume:
        resume = await self._resumes.get_by_id(resume_id)
        if resume is None:
            raise ResumeNotFoundError(resume_id)
        return resume

    async def list_resumes_for_job(self, job_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        return await self._resumes.list_by_job(job_id, skip=skip, limit=limit)

    async def download(self, resume_id: uuid.UUID) -> tuple[Resume, bytes]:
        resume = await self.get_resume(resume_id)
        content = await self._storage.read(resume.storage_path)
        return resume, content
