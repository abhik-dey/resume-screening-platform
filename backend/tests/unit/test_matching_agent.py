"""
MatchingAgent unit tests using in-memory fakes.

The most important behaviors under test: the score is unaffected by LLM
output, and an LLM failure never loses the computed score.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.matching.agent import MatchingAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.score import Score
from app.domain.entities.skill import SkillCategory
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from tests.fakes import ScriptedLLMProvider

ANALYSIS_JSON = """{
  "strengths": ["Has all required backend skills"],
  "weaknesses": ["No Kubernetes experience listed"]
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

    async def get_by_id(self, resume_id: uuid.UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        return [r for r in self._resumes.values() if r.job_id == job_id][skip : skip + limit]


class FakeJobRepository(JobRepository):
    def __init__(self) -> None:
        self._jobs: dict[uuid.UUID, Job] = {}

    async def create(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def update(self, job: Job) -> Job:
        self._jobs[job.id] = job
        return job

    async def get_by_id(self, job_id: uuid.UUID) -> Job | None:
        return self._jobs.get(job_id)

    async def list_all(self, skip: int = 0, limit: int = 50) -> list[Job]:
        return list(self._jobs.values())[skip : skip + limit]


class FakeResumeSkillRepository(ResumeSkillRepository):
    def __init__(self) -> None:
        self._skills: dict[uuid.UUID, list[ResumeSkillDetail]] = {}

    def set_skills(self, resume_id: uuid.UUID, names: list[str]) -> None:
        self._skills[resume_id] = [
            ResumeSkillDetail(
                skill_id=uuid.uuid4(), name=n, category=SkillCategory.PROGRAMMING, confidence=1.0
            )
            for n in names
        ]

    async def upsert(self, resume_id, skill_id, confidence) -> None:
        pass

    async def list_by_resume(self, resume_id: uuid.UUID) -> list[ResumeSkillDetail]:
        return self._skills.get(resume_id, [])


class FakeScoreRepository(ScoreRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, Score] = {}
        self.upsert_count = 0

    async def upsert(self, score: Score) -> Score:
        self.upsert_count += 1
        self._by_resume[score.resume_id] = score
        return score

    async def get_by_resume_id(self, resume_id: uuid.UUID) -> Score | None:
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID) -> list[Score]:
        return sorted(
            [s for s in self._by_resume.values() if s.job_id == job_id],
            key=lambda s: s.similarity_score,
            reverse=True,
        )

    async def update_rank(self, score_id: uuid.UUID, rank: int) -> None:
        for score in self._by_resume.values():
            if score.id == score_id:
                score.rank = rank
                return
        raise ValueError(f"score {score_id} not found")


class FakeAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.created: list[AuditLog] = []

    async def create(self, audit_log: AuditLog) -> AuditLog:
        self.created.append(audit_log)
        return audit_log


@pytest.fixture
def repos():
    return (
        FakeResumeRepository(),
        FakeJobRepository(),
        FakeResumeSkillRepository(),
        FakeScoreRepository(),
        FakeAuditLogRepository(),
    )


async def _setup(repos, candidate_skills=None, required_skills=None, status=ResumeStatus.PARSED):
    resume_repo, job_repo, skill_repo, score_repo, audit_repo = repos
    job = await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title="Backend Engineer",
            description="...",
            required_skills=required_skills if required_skills is not None else ["Python", "PostgreSQL"],
            preferred_skills=["Kubernetes"],
            min_experience_years=3,
            education_requirement="Bachelor",
            status=JobStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )
    )
    resume = await resume_repo.create(
        Resume(
            id=uuid.uuid4(),
            job_id=job.id,
            uploaded_by=uuid.uuid4(),
            storage_path="x.pdf",
            original_filename="x.pdf",
            status=status,
            parsed_data={
                "experience": [{"company": "Acme", "start_date": "2020", "end_date": "2024"}],
                "education": [{"institution": "MIT", "degree": "BSc", "field_of_study": "CS"}],
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    skill_repo.set_skills(
        resume.id, candidate_skills if candidate_skills is not None else ["Python", "PostgreSQL"]
    )
    return job, resume


def _make_agent(repos, llm):
    resume_repo, job_repo, skill_repo, score_repo, audit_repo = repos
    return MatchingAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        llm_provider=llm,
        model_name="test-model",
    )


async def test_successful_match_persists_score_and_analysis(repos):
    _, resume = await _setup(repos)
    _, _, _, score_repo, _ = repos
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))

    result = await agent.match(resume.id)

    assert result.success is True
    score = await score_repo.get_by_resume_id(resume.id)
    assert score is not None
    assert 0.0 <= score.similarity_score <= 1.0
    assert score.strengths == ["Has all required backend skills"]
    assert score.weaknesses == ["No Kubernetes experience listed"]
    assert score.explanation


async def test_llm_failure_still_persists_the_score(repos):
    # The whole point of computing the score arithmetically: an LLM outage
    # degrades the qualitative prose, never the number.
    _, resume = await _setup(repos)
    _, _, _, score_repo, _ = repos
    agent = _make_agent(repos, ScriptedLLMProvider(["garbage", "still garbage"]))

    result = await agent.match(resume.id)

    assert result.success is True
    score = await score_repo.get_by_resume_id(resume.id)
    assert score is not None
    assert score.similarity_score > 0
    assert score.strengths == []
    assert score.weaknesses == []
    assert result.output["qualitative_analysis_failed"] is True


async def test_score_is_identical_whether_llm_succeeds_or_fails(repos):
    _, resume_a = await _setup(repos)
    _, _, _, score_repo, _ = repos
    agent_ok = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))
    await agent_ok.match(resume_a.id)
    score_with_llm = (await score_repo.get_by_resume_id(resume_a.id)).similarity_score

    agent_fail = _make_agent(repos, ScriptedLLMProvider(["garbage", "garbage"]))
    await agent_fail.match(resume_a.id)
    score_without_llm = (await score_repo.get_by_resume_id(resume_a.id)).similarity_score

    assert score_with_llm == score_without_llm


async def test_missing_skills_are_reported(repos):
    _, resume = await _setup(repos, candidate_skills=["Python"], required_skills=["Python", "Go"])
    _, _, _, score_repo, _ = repos
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))

    await agent.match(resume.id)

    score = await score_repo.get_by_resume_id(resume.id)
    assert "Go" in score.missing_skills
    assert "Python" in score.skill_overlap


async def test_rematching_updates_rather_than_duplicating(repos):
    _, resume = await _setup(repos)
    _, _, _, score_repo, _ = repos
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))

    await agent.match(resume.id)
    first_id = (await score_repo.get_by_resume_id(resume.id)).id
    await agent.match(resume.id)
    second_id = (await score_repo.get_by_resume_id(resume.id)).id

    assert first_id == second_id  # same row updated, not a duplicate


async def test_rematching_preserves_rank_assigned_by_ranking_agent(repos):
    # rank belongs to the Ranking Agent (Phase 10) — a single re-match must
    # not silently clear it.
    _, resume = await _setup(repos)
    _, _, _, score_repo, _ = repos
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))
    await agent.match(resume.id)

    existing = await score_repo.get_by_resume_id(resume.id)
    existing.rank = 3
    await score_repo.upsert(existing)

    await agent.match(resume.id)
    assert (await score_repo.get_by_resume_id(resume.id)).rank == 3


async def test_unparsed_resume_fails_gracefully(repos):
    _, resume = await _setup(repos, status=ResumeStatus.UPLOADED)
    llm = ScriptedLLMProvider([ANALYSIS_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.match(resume.id)

    assert result.success is False
    assert "must be parsed" in result.reasoning.lower()
    assert llm.call_count == 0


async def test_resume_not_found_fails_gracefully(repos):
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))
    result = await agent.match(uuid.uuid4())
    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_audit_log_records_full_breakdown(repos):
    _, resume = await _setup(repos)
    _, _, _, _, audit_repo = repos
    agent = _make_agent(repos, ScriptedLLMProvider([ANALYSIS_JSON]))

    await agent.match(resume.id)

    assert len(audit_repo.created) == 1
    entry = audit_repo.created[0]
    assert entry.agent_name == "matching"
    assert entry.input_ref == f"resume:{resume.id}"
    assert "components" in entry.output["breakdown"]
    assert len(entry.output["breakdown"]["components"]) == 3
