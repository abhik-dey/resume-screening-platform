"""
SkillExtractionAgent unit tests using hand-rolled fakes — no real DB or LLM.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.skill_extractor.agent import SkillExtractionAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.skill import Skill, SkillCategory
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.skill_repository import SkillRepository
from tests.fakes import ScriptedLLMProvider


class FakeResumeRepository(ResumeRepository):
    def __init__(self) -> None:
        self._resumes: dict[uuid.UUID, Resume] = {}

    async def create(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def update(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def get_by_id(self, resume_id: uuid.UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        return [r for r in self._resumes.values() if r.job_id == job_id][skip : skip + limit]


class FakeSkillRepository(SkillRepository):
    def __init__(self) -> None:
        self._by_name: dict[str, Skill] = {}

    async def get_by_name(self, name: str) -> Skill | None:
        return self._by_name.get(name.lower())

    async def get_or_create(self, name: str, category: SkillCategory) -> Skill:
        existing = self._by_name.get(name.lower())
        if existing is not None:
            return existing
        skill = Skill(id=uuid.uuid4(), name=name, category=category, created_at=datetime.now(timezone.utc))
        self._by_name[name.lower()] = skill
        return skill


class FakeResumeSkillRepository(ResumeSkillRepository):
    def __init__(self, skill_repo: FakeSkillRepository) -> None:
        self._skill_repo = skill_repo
        self._links: dict[tuple[uuid.UUID, uuid.UUID], float | None] = {}

    async def upsert(self, resume_id: uuid.UUID, skill_id: uuid.UUID, confidence: float | None) -> None:
        self._links[(resume_id, skill_id)] = confidence

    async def list_by_resume(self, resume_id: uuid.UUID) -> list[ResumeSkillDetail]:
        details = []
        for (r_id, s_id), confidence in self._links.items():
            if r_id == resume_id:
                skill = next(s for s in self._skill_repo._by_name.values() if s.id == s_id)
                details.append(
                    ResumeSkillDetail(
                        skill_id=s_id,
                        name=skill.name,
                        category=skill.category,
                        confidence=confidence,
                    )
                )
        return details


class FakeAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.created: list[AuditLog] = []

    async def create(self, audit_log: AuditLog) -> AuditLog:
        self.created.append(audit_log)
        return audit_log


@pytest.fixture
def repos():
    """The four fakes every test in this module needs, wired together."""
    resume_repo = FakeResumeRepository()
    skill_repo = FakeSkillRepository()
    resume_skill_repo = FakeResumeSkillRepository(skill_repo)
    audit_repo = FakeAuditLogRepository()
    return resume_repo, skill_repo, resume_skill_repo, audit_repo


def _make_parsed_resume(skills: list[str]) -> Resume:
    return Resume(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        storage_path="irrelevant.pdf",
        original_filename="resume.pdf",
        status=ResumeStatus.PARSED,
        parsed_data={"skills": skills},
        created_at=datetime.now(timezone.utc),
    )


def _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo):
    return SkillExtractionAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        skill_repository=skill_repo,
        resume_skill_repository=resume_skill_repo,
        llm_provider=llm,
        model_name="test-model",
    )


async def test_dictionary_only_resume_needs_no_llm_call(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(_make_parsed_resume(["python", "C plus plus", "postgres"]))
    llm = ScriptedLLMProvider(["should never be called"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(resume.id)

    assert result.success is True
    assert llm.call_count == 0
    linked = await resume_skill_repo.list_by_resume(resume.id)
    assert {s.name for s in linked} == {"Python", "C++", "PostgreSQL"}
    assert all(s.confidence == 1.0 for s in linked)


async def test_unknown_skills_are_batched_into_a_single_llm_call(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(
        _make_parsed_resume(["python", "SomeObscureFramework", "AnotherWeirdTool"])
    )
    llm_response = (
        '{"skills": ['
        '{"raw": "SomeObscureFramework", "canonical_name": "Some Obscure Framework",'
        ' "category": "programming"},'
        '{"raw": "AnotherWeirdTool", "canonical_name": "Another Weird Tool", "category": "devops"}'
        "]}"
    )
    llm = ScriptedLLMProvider([llm_response])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(resume.id)

    assert result.success is True
    assert llm.call_count == 1  # exactly one batched call, not one per unknown skill
    linked = await resume_skill_repo.list_by_resume(resume.id)
    names = {s.name for s in linked}
    assert names == {"Python", "Some Obscure Framework", "Another Weird Tool"}
    llm_resolved = [s for s in linked if s.name != "Python"]
    assert all(s.confidence == 0.7 for s in llm_resolved)


async def test_llm_batch_failure_preserves_dictionary_hits_partial_success(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(_make_parsed_resume(["python", "TotallyUnknownThing"]))
    llm = ScriptedLLMProvider(["garbage", "still garbage"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(resume.id)

    assert result.success is True  # dictionary work still counts as success
    linked = await resume_skill_repo.list_by_resume(resume.id)
    assert {s.name for s in linked} == {"Python"}  # the unknown one was NOT force-linked
    assert "unresolved" in result.reasoning.lower() or "failed" in result.reasoning.lower()
    assert result.output["unresolved_raw_skills"] == ["TotallyUnknownThing"]


async def test_resume_not_parsed_fails_gracefully(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = Resume(
        id=uuid.uuid4(), job_id=uuid.uuid4(), uploaded_by=uuid.uuid4(),
        storage_path="x.pdf", original_filename="x.pdf",
        status=ResumeStatus.UPLOADED,  # not parsed yet
        created_at=datetime.now(timezone.utc),
    )
    await resume_repo.create(resume)
    llm = ScriptedLLMProvider(["irrelevant"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(resume.id)

    assert result.success is False
    assert "must be parsed" in result.reasoning.lower()
    assert llm.call_count == 0


async def test_resume_not_found_fails_gracefully(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    llm = ScriptedLLMProvider(["irrelevant"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(uuid.uuid4())

    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_empty_skills_list_succeeds_trivially(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(_make_parsed_resume([]))
    llm = ScriptedLLMProvider(["irrelevant"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    result = await agent.extract(resume.id)

    assert result.success is True
    assert llm.call_count == 0
    assert result.output["resolved_skills"] == []


async def test_rerunning_the_agent_is_idempotent(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(_make_parsed_resume(["python", "java"]))
    llm = ScriptedLLMProvider(["irrelevant"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    await agent.extract(resume.id)
    await agent.extract(resume.id)  # re-run should not duplicate or error

    linked = await resume_skill_repo.list_by_resume(resume.id)
    assert len(linked) == 2  # not 4


async def test_audit_log_written_with_correct_agent_name(repos):
    resume_repo, skill_repo, resume_skill_repo, audit_repo = repos
    resume = await resume_repo.create(_make_parsed_resume(["python"]))
    llm = ScriptedLLMProvider(["irrelevant"])
    agent = _make_agent(resume_repo, skill_repo, resume_skill_repo, llm, audit_repo)

    await agent.extract(resume.id)

    assert len(audit_repo.created) == 1
    assert audit_repo.created[0].agent_name == "skill_extractor"
    assert audit_repo.created[0].input_ref == f"resume:{resume.id}"
