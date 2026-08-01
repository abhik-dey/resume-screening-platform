"""
ResumeService unit tests using hand-rolled in-memory fakes instead of
SQLAlchemy or the filesystem — the payoff of depending on abstract
interfaces (JobRepository, ResumeRepository, FileStorage).
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.validation.resume_file import UnsupportedFileTypeError
from app.services.resume_service import (
    JobNotFoundError,
    JobNotOpenError,
    ResumeNotFoundError,
    ResumeService,
)

MAX_SIZE = 10 * 1024 * 1024


class FakeJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, Job] = {}

    async def create(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        return self._jobs.get(job_id)

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Job]:
        return list(self._jobs.values())[skip : skip + limit]


class FakeResumeRepository(ResumeRepository):
    def __init__(self) -> None:
        self._resumes: dict[uuid.UUID, Resume] = {}

    async def create(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def get_by_id(self, resume_id: uuid.UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        matches = [r for r in self._resumes.values() if r.job_id == job_id]
        return matches[skip : skip + limit]


class FakeFileStorage(FileStorage):
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}

    async def save(self, content: bytes, filename: str) -> str:
        key = f"{uuid.uuid4()}-{filename}"
        self._files[key] = content
        return key

    async def read(self, storage_path: str) -> bytes:
        return self._files[storage_path]

    async def delete(self, storage_path: str) -> None:
        self._files.pop(storage_path, None)


@pytest.fixture
def job_repo() -> FakeJobRepository:
    return FakeJobRepository()


@pytest.fixture
def resume_repo() -> FakeResumeRepository:
    return FakeResumeRepository()


@pytest.fixture
def file_storage() -> FakeFileStorage:
    return FakeFileStorage()


@pytest.fixture
def resume_service(resume_repo, job_repo, file_storage) -> ResumeService:
    return ResumeService(
        resume_repository=resume_repo,
        job_repository=job_repo,
        file_storage=file_storage,
        max_upload_size_bytes=MAX_SIZE,
    )


async def _make_open_job(job_repo: FakeJobRepository) -> Job:
    job = Job(
        id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Backend Engineer",
        description="...",
        status=JobStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )
    return await job_repo.create(job)


async def test_upload_succeeds_for_open_job(resume_service, job_repo):
    job = await _make_open_job(job_repo)
    resume = await resume_service.upload(
        job_id=job.id, uploaded_by=uuid.uuid4(), filename="resume.pdf", content=b"%PDF fake content"
    )
    assert resume.job_id == job.id
    assert resume.status.value == "uploaded"
    assert resume.candidate_id is None


async def test_upload_rejected_for_nonexistent_job(resume_service):
    with pytest.raises(JobNotFoundError):
        await resume_service.upload(
            job_id=uuid.uuid4(), uploaded_by=uuid.uuid4(), filename="resume.pdf", content=b"%PDF x"
        )


async def test_upload_rejected_for_closed_job(resume_service, job_repo):
    job = Job(
        id=uuid.uuid4(), created_by=uuid.uuid4(), title="Old Role", description="...",
        status=JobStatus.CLOSED, created_at=datetime.now(timezone.utc),
    )
    await job_repo.create(job)
    with pytest.raises(JobNotOpenError):
        await resume_service.upload(
            job_id=job.id, uploaded_by=uuid.uuid4(), filename="resume.pdf", content=b"%PDF x"
        )


async def test_upload_rejected_for_invalid_file_type(resume_service, job_repo):
    job = await _make_open_job(job_repo)
    with pytest.raises(UnsupportedFileTypeError):
        await resume_service.upload(
            job_id=job.id, uploaded_by=uuid.uuid4(), filename="resume.exe", content=b"MZ x"
        )


async def test_get_resume_not_found_raises(resume_service):
    with pytest.raises(ResumeNotFoundError):
        await resume_service.get_resume(uuid.uuid4())


async def test_download_returns_original_bytes(resume_service, job_repo):
    job = await _make_open_job(job_repo)
    uploaded = await resume_service.upload(
        job_id=job.id, uploaded_by=uuid.uuid4(), filename="resume.pdf", content=b"%PDF original bytes"
    )
    resume, content = await resume_service.download(uploaded.id)
    assert resume.id == uploaded.id
    assert content == b"%PDF original bytes"


async def test_list_resumes_for_job_filters_correctly(resume_service, job_repo):
    job_a = await _make_open_job(job_repo)
    job_b = await _make_open_job(job_repo)
    await resume_service.upload(
        job_id=job_a.id, uploaded_by=uuid.uuid4(), filename="a.pdf", content=b"%PDF a"
    )
    await resume_service.upload(
        job_id=job_b.id, uploaded_by=uuid.uuid4(), filename="b.pdf", content=b"%PDF b"
    )

    results = await resume_service.list_resumes_for_job(job_a.id)
    assert len(results) == 1
    assert results[0].original_filename == "a.pdf"
