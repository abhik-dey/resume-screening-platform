"""
JobDescriptionAgent unit tests using in-memory fakes.

The merge policy gets the most attention here — silently overwriting a
recruiter's deliberate input with an LLM guess is the highest-consequence
bug this agent could have.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.job_description.agent import JobDescriptionAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.job import Job, JobStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.job_repository import JobRepository
from tests.fakes import ScriptedLLMProvider

FULL_EXTRACTION_JSON = """{
  "required_skills": ["python", "postgres"],
  "preferred_skills": ["k8s"],
  "min_experience_years": 5,
  "education_requirement": "BSc in Computer Science",
  "responsibilities": ["Design APIs", "Mentor juniors"],
  "keywords": ["backend", "distributed systems"]
}"""


class FakeJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, Job] = {}
        self.update_call_count = 0

    async def create(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def update(self, job: Job) -> Job:
        self.update_call_count += 1
        self._jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        return self._jobs.get(job_id)

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Job]:
        return list(self._jobs.values())[skip : skip + limit]


class FakeAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.created: list[AuditLog] = []

    async def create(self, audit_log: AuditLog) -> AuditLog:
        self.created.append(audit_log)
        return audit_log


@pytest.fixture
def repos():
    return FakeJobRepository(), FakeAuditLogRepository()


def _make_job(**overrides) -> Job:
    defaults = {
        "id": uuid.uuid4(),
        "created_by": uuid.uuid4(),
        "title": "Senior Backend Engineer",
        "description": "We need someone with Python and Postgres. 5+ years required.",
        "required_skills": [],
        "preferred_skills": [],
        "min_experience_years": None,
        "education_requirement": None,
        "responsibilities": [],
        "keywords": [],
        "status": JobStatus.OPEN,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Job(**defaults)


def _make_agent(job_repo, audit_repo, llm):
    return JobDescriptionAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        llm_provider=llm,
        model_name="test-model",
    )


async def test_empty_job_fields_are_filled_from_extraction(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job())
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    result = await agent.analyze(job.id)

    assert result.success is True
    updated = await job_repo.get_by_id(job.id)
    assert updated.min_experience_years == 5
    assert updated.education_requirement == "BSc in Computer Science"
    assert updated.responsibilities == ["Design APIs", "Mentor juniors"]
    assert set(result.output["applied_fields"]) == {
        "required_skills", "preferred_skills", "min_experience_years",
        "education_requirement", "responsibilities", "keywords",
    }
    assert result.output["skipped_fields"] == []


async def test_extracted_skills_are_normalized_to_canonical_names(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job())
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    await agent.analyze(job.id)

    updated = await job_repo.get_by_id(job.id)
    # "python" -> "Python", "postgres" -> "PostgreSQL", "k8s" -> "Kubernetes".
    # This canonical vocabulary must match what the Skill Extraction Agent
    # produces for resumes, or Phase 9 matching would silently mis-score.
    assert updated.required_skills == ["Python", "PostgreSQL"]
    assert updated.preferred_skills == ["Kubernetes"]


async def test_recruiter_provided_fields_are_not_overwritten_by_default(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(
        _make_job(required_skills=["Go", "Rust"], min_experience_years=10)
    )
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    result = await agent.analyze(job.id)

    updated = await job_repo.get_by_id(job.id)
    assert updated.required_skills == ["Go", "Rust"]  # recruiter's input preserved
    assert updated.min_experience_years == 10
    assert set(result.output["skipped_fields"]) == {"required_skills", "min_experience_years"}
    # Empty fields still get filled in the same pass.
    assert updated.responsibilities == ["Design APIs", "Mentor juniors"]
    # The extraction is still visible as a suggestion even though not applied.
    assert result.output["extracted"]["required_skills"] == ["Python", "PostgreSQL"]


async def test_overwrite_flag_replaces_recruiter_values(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(
        _make_job(required_skills=["Go", "Rust"], min_experience_years=10)
    )
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    result = await agent.analyze(job.id, overwrite=True)

    updated = await job_repo.get_by_id(job.id)
    assert updated.required_skills == ["Python", "PostgreSQL"]
    assert updated.min_experience_years == 5
    assert result.output["skipped_fields"] == []


async def test_empty_extraction_never_erases_existing_data_even_with_overwrite(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(
        _make_job(required_skills=["Go"], min_experience_years=7, keywords=["backend"])
    )
    empty_extraction = """{
      "required_skills": [], "preferred_skills": [],
      "min_experience_years": null, "education_requirement": null,
      "responsibilities": [], "keywords": []
    }"""
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([empty_extraction]))

    result = await agent.analyze(job.id, overwrite=True)

    updated = await job_repo.get_by_id(job.id)
    # "The LLM found nothing" is not a reason to erase recruiter data.
    assert updated.required_skills == ["Go"]
    assert updated.min_experience_years == 7
    assert updated.keywords == ["backend"]
    assert result.output["applied_fields"] == []


async def test_no_update_call_when_nothing_to_apply(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job(required_skills=["Go"]))
    empty_extraction = """{
      "required_skills": [], "preferred_skills": [],
      "min_experience_years": null, "education_requirement": null,
      "responsibilities": [], "keywords": []
    }"""
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([empty_extraction]))

    await agent.analyze(job.id)

    assert job_repo.update_call_count == 0  # avoid a pointless DB write


async def test_duplicate_skills_collapse_after_normalization(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job())
    dupes = """{
      "required_skills": ["python", "Python", "PYTHON", "py"],
      "preferred_skills": [], "min_experience_years": null,
      "education_requirement": null, "responsibilities": [], "keywords": []
    }"""
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([dupes]))

    await agent.analyze(job.id)

    updated = await job_repo.get_by_id(job.id)
    assert updated.required_skills == ["Python"]


async def test_unknown_skills_are_kept_not_dropped(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job())
    niche = """{
      "required_skills": ["python", "AcmeInternalFramework"],
      "preferred_skills": [], "min_experience_years": null,
      "education_requirement": null, "responsibilities": [], "keywords": []
    }"""
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([niche]))

    await agent.analyze(job.id)

    updated = await job_repo.get_by_id(job.id)
    # A niche in-house tool is still a real requirement — keep it.
    assert updated.required_skills == ["Python", "AcmeInternalFramework"]


async def test_job_not_found_fails_gracefully(repos):
    job_repo, audit_repo = repos
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    result = await agent.analyze(uuid.uuid4())

    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_empty_description_fails_gracefully(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job(description="   "))
    llm = ScriptedLLMProvider([FULL_EXTRACTION_JSON])
    agent = _make_agent(job_repo, audit_repo, llm)

    result = await agent.analyze(job.id)

    assert result.success is False
    assert "empty description" in result.reasoning.lower()
    assert llm.call_count == 0  # don't waste an API call on empty input


async def test_malformed_llm_output_retries_then_fails(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job())
    llm = ScriptedLLMProvider(["garbage", "still garbage"])
    agent = _make_agent(job_repo, audit_repo, llm)

    result = await agent.analyze(job.id)

    assert result.success is False
    assert llm.call_count == 2


async def test_audit_log_records_extracted_and_applied(repos):
    job_repo, audit_repo = repos
    job = await job_repo.create(_make_job(required_skills=["Go"]))
    agent = _make_agent(job_repo, audit_repo, ScriptedLLMProvider([FULL_EXTRACTION_JSON]))

    await agent.analyze(job.id)

    assert len(audit_repo.created) == 1
    entry = audit_repo.created[0]
    assert entry.agent_name == "job_description"
    assert entry.input_ref == f"job:{job.id}"
    # Both what was extracted AND what was applied are traceable, so a
    # divergence between the two is visible after the fact.
    assert entry.output["extracted"]["required_skills"] == ["Python", "PostgreSQL"]
    assert "required_skills" in entry.output["skipped_fields"]
