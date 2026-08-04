"""
RAGService unit tests.

Emphasis on hallucination resistance: what happens when the LLM cites
sources that don't exist, cites nothing, or answers confidently from
nothing. Those are the cases that matter in a hiring system.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.domain.entities.candidate import Candidate
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.skill import SkillCategory
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.infrastructure.embeddings.hash_embedding_provider import HashEmbeddingProvider
from app.infrastructure.vector_store.in_memory_vector_store import InMemoryVectorStore
from app.services.indexing_service import IndexingService
from app.services.rag_service import RAGError, RAGService
from tests.fakes import ScriptedLLMProvider

GROUNDED_ANSWER = """{
  "answer": "Jane Doe has Kubernetes experience [1].",
  "claims": [{"text": "Jane Doe has Kubernetes experience.", "source_ids": [1]}],
  "insufficient_evidence": false
}"""

FABRICATED_CITATIONS = """{
  "answer": "Three candidates have 10 years of Kubernetes experience [7][8].",
  "claims": [
    {"text": "Three candidates have 10 years of Kubernetes experience.", "source_ids": [7, 8]}
  ],
  "insufficient_evidence": false
}"""

UNCITED_ANSWER = """{
  "answer": "Jane is clearly the strongest candidate available.",
  "claims": [{"text": "Jane is clearly the strongest candidate available.", "source_ids": []}],
  "insufficient_evidence": false
}"""

INSUFFICIENT_ANSWER = """{
  "answer": "The retrieved resumes do not mention Rust experience.",
  "claims": [],
  "insufficient_evidence": true
}"""

PARTIALLY_GROUNDED = """{
  "answer": "Jane knows Kubernetes [1]. Bob has 20 years of experience [9].",
  "claims": [
    {"text": "Jane knows Kubernetes.", "source_ids": [1]},
    {"text": "Bob has 20 years of experience.", "source_ids": [9]}
  ],
  "insufficient_evidence": false
}"""


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


class FakeCandidateRepository(CandidateRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Candidate] = {}

    async def get_by_email(self, email):
        return next((c for c in self._by_id.values() if c.email == email), None)

    async def get_by_id(self, candidate_id):
        return self._by_id.get(candidate_id)

    async def create(self, candidate: Candidate) -> Candidate:
        self._by_id[candidate.id] = candidate
        return candidate


@pytest.fixture
def parts():
    resume_repo = FakeResumeRepository()
    skill_repo = FakeResumeSkillRepository()
    job_repo = FakeJobRepository()
    candidate_repo = FakeCandidateRepository()
    indexing = IndexingService(
        embedding_provider=HashEmbeddingProvider(dimensions=128),
        vector_store=InMemoryVectorStore(),
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        job_repository=job_repo,
    )
    return indexing, resume_repo, skill_repo, job_repo, candidate_repo


def _make_service(parts, llm):
    indexing, resume_repo, skill_repo, _, candidate_repo = parts
    return RAGService(
        indexing_service=indexing,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        candidate_repository=candidate_repo,
        llm_provider=llm,
    )


async def _index_candidate(parts, name="Jane Doe", skills=None):
    indexing, resume_repo, skill_repo, job_repo, candidate_repo = parts
    job = await job_repo.create(
        Job(
            id=uuid.uuid4(), created_by=uuid.uuid4(), title="Backend Engineer",
            description="Build APIs.", required_skills=["Python"], preferred_skills=[],
            status=JobStatus.OPEN, created_at=datetime.now(timezone.utc),
        )
    )
    candidate = await candidate_repo.create(
        Candidate(
            id=uuid.uuid4(), full_name=name, email=f"{name.replace(' ', '.').lower()}@example.com",
            created_at=datetime.now(timezone.utc),
        )
    )
    resume = await resume_repo.create(
        Resume(
            id=uuid.uuid4(), job_id=job.id, uploaded_by=uuid.uuid4(),
            candidate_id=candidate.id, storage_path="x.pdf", original_filename="x.pdf",
            status=ResumeStatus.PARSED,
            parsed_data={
                "experience": [
                    {
                        "title": "Engineer",
                        "company": "Acme",
                        "description": "Built Kubernetes clusters",
                    }
                ],
                "projects": [],
                "education": [],
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    skill_repo.set_skills(resume.id, skills if skills is not None else ["Kubernetes", "Python"])
    await indexing.index_resume(resume.id)
    return job, resume, candidate


async def test_grounded_answer_is_returned_with_sources(parts):
    await _index_candidate(parts)
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))

    result = await service.ask("Who has Kubernetes experience?")

    assert len(result.claims) == 1
    assert result.claims[0].source_ids == [1]
    assert result.answer_rejected is False
    # Source text is returned so any claim can be verified independently.
    assert len(result.sources) == 1
    assert result.sources[0].text


async def test_fabricated_citations_cause_the_answer_to_be_rejected(parts):
    # The central hallucination case: the model invents sources to support
    # a confident claim about real people.
    await _index_candidate(parts)
    service = _make_service(parts, ScriptedLLMProvider([FABRICATED_CITATIONS]))

    result = await service.ask("Who has 10 years of Kubernetes experience?")

    assert result.answer_rejected is True
    assert result.claims == []
    assert "withheld" in result.answer.lower()
    assert result.citation_warnings
    # Sources are still returned for manual review.
    assert len(result.sources) == 1


async def test_uncited_claims_cause_rejection(parts):
    await _index_candidate(parts)
    service = _make_service(parts, ScriptedLLMProvider([UNCITED_ANSWER]))

    result = await service.ask("Who is the best candidate?")

    assert result.answer_rejected is True
    assert result.claims == []


async def test_partially_grounded_answer_keeps_valid_claims_only(parts):
    await _index_candidate(parts)
    service = _make_service(parts, ScriptedLLMProvider([PARTIALLY_GROUNDED]))

    result = await service.ask("Tell me about the candidates.")

    assert result.answer_rejected is False
    assert len(result.claims) == 1
    assert "Jane knows Kubernetes." in result.claims[0].text
    # The fabricated claim was stripped, and that's disclosed rather than silent.
    assert result.citation_warnings


async def test_insufficient_evidence_is_reported_honestly(parts):
    # "I can't tell from these sources" must be a first-class outcome, not
    # something the model papers over with a plausible guess.
    await _index_candidate(parts)
    service = _make_service(parts, ScriptedLLMProvider([INSUFFICIENT_ANSWER]))

    result = await service.ask("Who has Rust experience?")

    assert result.insufficient_evidence is True
    assert result.answer_rejected is False


async def test_no_indexed_resumes_returns_a_clear_message(parts):
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))

    result = await service.ask("Who knows Python?")

    assert result.insufficient_evidence is True
    assert "index" in result.answer.lower()
    assert result.sources == []


async def test_empty_question_is_rejected(parts):
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))
    with pytest.raises(RAGError, match="cannot be empty"):
        await service.ask("   ")


async def test_out_of_range_top_k_is_rejected(parts):
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))
    with pytest.raises(RAGError, match="top_k"):
        await service.ask("Who knows Python?", top_k=500)


async def test_malformed_llm_output_retries_then_raises(parts):
    await _index_candidate(parts)
    llm = ScriptedLLMProvider(["garbage", "still garbage"])
    service = _make_service(parts, llm)

    with pytest.raises(RAGError, match="valid answer"):
        await service.ask("Who knows Kubernetes?")
    assert llm.call_count == 2


async def test_top_k_limits_retrieved_sources(parts):
    for i in range(5):
        await _index_candidate(parts, name=f"Candidate {i}")
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))

    result = await service.ask("Who knows Kubernetes?", top_k=2)

    assert len(result.sources) == 2


async def test_sources_are_numbered_from_one(parts):
    for i in range(3):
        await _index_candidate(parts, name=f"Candidate {i}")
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))

    result = await service.ask("Who knows Kubernetes?")

    assert [s.source_id for s in result.sources] == [1, 2, 3]


async def test_candidate_names_are_resolved_in_sources(parts):
    await _index_candidate(parts, name="Alice Smith")
    service = _make_service(parts, ScriptedLLMProvider([GROUNDED_ANSWER]))

    result = await service.ask("Who knows Kubernetes?")

    assert result.sources[0].candidate_name == "Alice Smith"
