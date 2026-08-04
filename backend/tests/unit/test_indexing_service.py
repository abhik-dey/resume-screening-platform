"""IndexingService unit tests with in-memory fakes."""
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.skill import SkillCategory
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.search.text_builder import build_job_text, build_resume_text
from app.infrastructure.embeddings.hash_embedding_provider import HashEmbeddingProvider
from app.infrastructure.vector_store.in_memory_vector_store import InMemoryVectorStore
from app.services.indexing_service import IndexingError, IndexingService


class FakeResumeRepository(ResumeRepository):
    def __init__(self) -> None:
        self._resumes: dict[uuid.UUID, Resume] = {}

    async def create(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def update(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def get_by_id(self, resume_id):
        return self._resumes.get(resume_id)

    async def list_by_job(self, job_id, skip: int = 0, limit: int = 50):
        return [r for r in self._resumes.values() if r.job_id == job_id]


class FakeJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, Job] = {}

    async def create(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def update(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def get_by_id(self, job_id):
        return self._jobs.get(job_id)

    async def list_all(self, skip: int = 0, limit: int = 50):
        return list(self._jobs.values())


class FakeResumeSkillRepository(ResumeSkillRepository):
    def __init__(self) -> None:
        self._skills: dict[uuid.UUID, list[ResumeSkillDetail]] = {}

    def set_skills(self, resume_id, names):
        self._skills[resume_id] = [
            ResumeSkillDetail(
                skill_id=uuid.uuid4(), name=n, category=SkillCategory.PROGRAMMING, confidence=1.0
            )
            for n in names
        ]

    async def upsert(self, resume_id, skill_id, confidence) -> None:
        pass

    async def list_by_resume(self, resume_id):
        return self._skills.get(resume_id, [])


@pytest.fixture
def service_parts():
    resume_repo = FakeResumeRepository()
    skill_repo = FakeResumeSkillRepository()
    job_repo = FakeJobRepository()
    store = InMemoryVectorStore()
    service = IndexingService(
        embedding_provider=HashEmbeddingProvider(dimensions=128),
        vector_store=store,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        job_repository=job_repo,
    )
    return service, resume_repo, skill_repo, job_repo, store


async def _make_resume(resume_repo, skill_repo, job_id, skills, status=ResumeStatus.PARSED):
    resume = await resume_repo.create(
        Resume(
            id=uuid.uuid4(),
            job_id=job_id,
            uploaded_by=uuid.uuid4(),
            storage_path="x.pdf",
            original_filename="x.pdf",
            status=status,
            parsed_data={
                "experience": [{"title": "Engineer", "company": "Acme", "description": "Built APIs"}],
                "projects": [{"name": "Payments", "description": "Payment service", "technologies": skills}],
                "education": [],
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    skill_repo.set_skills(resume.id, skills)
    return resume


async def _make_job(job_repo, title="Backend Engineer", skills=None):
    return await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title=title,
            description="Build and scale APIs.",
            required_skills=skills if skills is not None else ["Python", "PostgreSQL"],
            preferred_skills=[],
            status=JobStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )
    )


async def test_index_resume_stores_a_vector(service_parts):
    service, resume_repo, skill_repo, job_repo, store = service_parts
    job = await _make_job(job_repo)
    resume = await _make_resume(resume_repo, skill_repo, job.id, ["Python", "PostgreSQL"])

    result = await service.index_resume(resume.id)

    assert result["dimensions"] == 128
    assert result["text_length"] > 0
    hits = await store.search("resumes", [0.0] * 128, limit=10)
    assert len(hits) == 1


async def test_index_resume_requires_parsed_status(service_parts):
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    job = await _make_job(job_repo)
    resume = await _make_resume(
        resume_repo, skill_repo, job.id, ["Python"], status=ResumeStatus.UPLOADED
    )

    with pytest.raises(IndexingError, match="must be parsed"):
        await service.index_resume(resume.id)


async def test_index_nonexistent_resume_raises(service_parts):
    service = service_parts[0]
    with pytest.raises(IndexingError, match="not found"):
        await service.index_resume(uuid.uuid4())


async def test_reindexing_replaces_rather_than_duplicates(service_parts):
    service, resume_repo, skill_repo, job_repo, store = service_parts
    job = await _make_job(job_repo)
    resume = await _make_resume(resume_repo, skill_repo, job.id, ["Python"])

    await service.index_resume(resume.id)
    await service.index_resume(resume.id)

    hits = await store.search("resumes", [0.0] * 128, limit=10)
    assert len(hits) == 1


async def test_index_job_stores_a_vector(service_parts):
    service, _, _, job_repo, store = service_parts
    job = await _make_job(job_repo)

    result = await service.index_job(job.id)

    assert result["dimensions"] == 128
    hits = await store.search("jobs", [0.0] * 128, limit=10)
    assert len(hits) == 1


async def test_search_finds_the_most_relevant_resume(service_parts):
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    job = await _make_job(job_repo)
    backend = await _make_resume(
        resume_repo, skill_repo, job.id, ["Python", "PostgreSQL", "Django"]
    )
    designer = await _make_resume(
        resume_repo, skill_repo, job.id, ["Photoshop", "Illustrator", "Typography"]
    )
    await service.index_resume(backend.id)
    await service.index_resume(designer.id)

    results = await service.search_resumes("Python PostgreSQL Django backend")

    assert results[0].entity_id == backend.id
    assert results[0].score > results[1].score


async def test_search_rejects_an_empty_query(service_parts):
    service = service_parts[0]
    with pytest.raises(IndexingError, match="cannot be empty"):
        await service.search_resumes("   ")


async def test_search_can_be_filtered_to_one_job(service_parts):
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    job_a = await _make_job(job_repo, title="Backend")
    job_b = await _make_job(job_repo, title="Frontend")
    resume_a = await _make_resume(resume_repo, skill_repo, job_a.id, ["Python"])
    resume_b = await _make_resume(resume_repo, skill_repo, job_b.id, ["Python"])
    await service.index_resume(resume_a.id)
    await service.index_resume(resume_b.id)

    results = await service.search_resumes("Python", job_id=job_a.id)

    assert len(results) == 1
    assert results[0].entity_id == resume_a.id


async def test_search_respects_the_limit(service_parts):
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    job = await _make_job(job_repo)
    for _ in range(5):
        resume = await _make_resume(resume_repo, skill_repo, job.id, ["Python"])
        await service.index_resume(resume.id)

    assert len(await service.search_resumes("Python", limit=2)) == 2


async def test_find_similar_candidates_for_a_job(service_parts):
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    job = await _make_job(job_repo, skills=["Python", "PostgreSQL"])
    matching = await _make_resume(resume_repo, skill_repo, job.id, ["Python", "PostgreSQL"])
    unrelated = await _make_resume(resume_repo, skill_repo, job.id, ["Photoshop", "Illustrator"])
    await service.index_resume(matching.id)
    await service.index_resume(unrelated.id)

    results = await service.find_similar_candidates(job.id)

    assert results[0].entity_id == matching.id


async def test_cross_job_search_surfaces_candidates_from_other_roles(service_parts):
    # The genuinely useful case: a strong candidate who applied elsewhere,
    # which keyword search over one job's applicants would never reveal.
    service, resume_repo, skill_repo, job_repo, _ = service_parts
    target_job = await _make_job(job_repo, skills=["Python", "PostgreSQL"])
    other_job = await _make_job(job_repo, title="Data Engineer")
    other_applicant = await _make_resume(
        resume_repo, skill_repo, other_job.id, ["Python", "PostgreSQL"]
    )
    await service.index_resume(other_applicant.id)

    restricted = await service.find_similar_candidates(target_job.id, restrict_to_job=True)
    unrestricted = await service.find_similar_candidates(target_job.id, restrict_to_job=False)

    assert restricted == []
    assert len(unrestricted) == 1
    assert unrestricted[0].entity_id == other_applicant.id


async def test_similar_candidates_for_nonexistent_job_raises(service_parts):
    service = service_parts[0]
    with pytest.raises(IndexingError, match="not found"):
        await service.find_similar_candidates(uuid.uuid4())


async def test_payload_records_the_embedding_model(service_parts):
    # Vectors from different models aren't comparable, so knowing which
    # produced a given vector matters if the provider ever changes.
    service, resume_repo, skill_repo, job_repo, store = service_parts
    job = await _make_job(job_repo)
    resume = await _make_resume(resume_repo, skill_repo, job.id, ["Python"])
    await service.index_resume(resume.id)

    hits = await store.search("resumes", [0.0] * 128, limit=1)
    assert "embedding_model" in hits[0].payload


async def test_resume_text_excludes_personal_identifiers():
    # Names and emails add no capability signal and invite matching on the
    # wrong things entirely.
    resume = Resume(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        storage_path="x.pdf",
        original_filename="x.pdf",
        status=ResumeStatus.PARSED,
        parsed_data={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-1234",
            "experience": [{"title": "Engineer", "company": "Acme", "description": "Built APIs"}],
        },
        created_at=datetime.now(timezone.utc),
    )
    text = build_resume_text(resume, ["Python"])
    assert "Jane Doe" not in text
    assert "jane@example.com" not in text
    assert "555-1234" not in text
    assert "Python" in text


async def test_job_text_includes_requirements():
    job = Job(
        id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Backend Engineer",
        description="Build APIs.",
        required_skills=["Python"],
        preferred_skills=["Go"],
        responsibilities=["Design services"],
        status=JobStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )
    text = build_job_text(job)
    assert "Backend Engineer" in text
    assert "Python" in text
    assert "Go" in text
    assert "Design services" in text
