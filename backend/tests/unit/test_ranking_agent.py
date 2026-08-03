"""RankingAgent unit tests using in-memory fakes. No LLM involved anywhere."""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.ranking.agent import RankingAgent
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
from app.domain.matching.scorer import ScoringWeights


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


class FakeScoreRepository(ScoreRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, Score] = {}
        self.rank_updates: list[tuple[uuid.UUID, int]] = []

    async def upsert(self, score: Score) -> Score:
        self._by_resume[score.resume_id] = score
        return score

    async def get_by_resume_id(self, resume_id: uuid.UUID) -> Score | None:
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID) -> list[Score]:
        return [s for s in self._by_resume.values() if s.job_id == job_id]

    async def update_rank(self, score_id: uuid.UUID, rank: int) -> None:
        self.rank_updates.append((score_id, rank))
        for score in self._by_resume.values():
            if score.id == score_id:
                score.rank = rank
                return
        raise ValueError(f"score {score_id} not found")


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


class FakeAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.created: list[AuditLog] = []

    async def create(self, audit_log: AuditLog) -> AuditLog:
        self.created.append(audit_log)
        return audit_log


@pytest.fixture
def repos():
    return (
        FakeJobRepository(),
        FakeScoreRepository(),
        FakeResumeRepository(),
        FakeResumeSkillRepository(),
        FakeAuditLogRepository(),
    )


def _make_agent(repos):
    job_repo, score_repo, resume_repo, skill_repo, audit_repo = repos
    return RankingAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
    )


async def _setup_job(repos, required_skills=None) -> Job:
    job_repo = repos[0]
    return await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title="Backend Engineer",
            description="...",
            required_skills=required_skills if required_skills is not None else ["Python", "Go"],
            preferred_skills=[],
            min_experience_years=5,
            education_requirement="Bachelor",
            status=JobStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )
    )


async def _add_candidate(repos, job: Job, similarity: float, skills: list[str] | None = None) -> Score:
    _, score_repo, resume_repo, skill_repo, _ = repos
    resume = await resume_repo.create(
        Resume(
            id=uuid.uuid4(),
            job_id=job.id,
            uploaded_by=uuid.uuid4(),
            storage_path="x.pdf",
            original_filename="x.pdf",
            status=ResumeStatus.PARSED,
            parsed_data={
                "experience": [{"company": "A", "start_date": "2015", "end_date": "2025"}],
                "education": [{"institution": "MIT", "degree": "PhD"}],
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    skill_repo.set_skills(resume.id, skills if skills is not None else ["Python"])
    return await score_repo.upsert(
        Score(
            id=uuid.uuid4(),
            resume_id=resume.id,
            job_id=job.id,
            similarity_score=similarity,
            skill_overlap=skills if skills is not None else ["Python"],
            missing_skills=[],
            strengths=[],
            weaknesses=[],
            rank=None,
            explanation=None,
            created_at=datetime.now(timezone.utc),
        )
    )


async def test_ranks_are_persisted_best_first(repos):
    job = await _setup_job(repos)
    await _add_candidate(repos, job, 0.4)
    await _add_candidate(repos, job, 0.9)
    await _add_candidate(repos, job, 0.6)
    score_repo = repos[1]
    agent = _make_agent(repos)

    result = await agent.rank(job.id)

    assert result.success is True
    scores = sorted(await score_repo.list_by_job(job.id), key=lambda s: s.rank)
    assert [s.similarity_score for s in scores] == [0.9, 0.6, 0.4]
    assert [s.rank for s in scores] == [1, 2, 3]


async def test_job_with_no_scored_candidates_succeeds_trivially(repos):
    job = await _setup_job(repos)
    agent = _make_agent(repos)

    result = await agent.rank(job.id)

    assert result.success is True
    assert result.output["total_candidates"] == 0
    assert "run matching" in result.reasoning.lower()


async def test_job_not_found_fails_gracefully(repos):
    agent = _make_agent(repos)
    result = await agent.rank(uuid.uuid4())
    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_ranking_is_repeatable(repos):
    job = await _setup_job(repos)
    for similarity in [0.5, 0.5, 0.8, 0.3]:
        await _add_candidate(repos, job, similarity)
    score_repo = repos[1]
    agent = _make_agent(repos)

    await agent.rank(job.id)
    first = {str(s.resume_id): s.rank for s in await score_repo.list_by_job(job.id)}
    await agent.rank(job.id)
    second = {str(s.resume_id): s.rank for s in await score_repo.list_by_job(job.id)}

    assert first == second


async def test_custom_weights_rescore_and_can_change_the_order(repos):
    job = await _setup_job(repos, required_skills=["Python", "Go"])
    # Candidate A: both required skills, so a perfect skills score.
    await _add_candidate(repos, job, 0.5, skills=["Python", "Go"])
    # Candidate B: only one, but the stale stored score is higher.
    await _add_candidate(repos, job, 0.95, skills=["Python"])
    score_repo = repos[1]
    agent = _make_agent(repos)

    result = await agent.rank(
        job.id, weights=ScoringWeights(skills=1.0, experience=0.0, education=0.0)
    )

    assert result.success is True
    assert result.output["weights_applied"]["skills"] == 1.0
    ranked = sorted(await score_repo.list_by_job(job.id), key=lambda s: s.rank)
    # Re-scored on skills alone, the fully-skilled candidate now leads.
    assert ranked[0].skill_overlap == ["Python", "Go"]


async def test_ranking_without_weights_does_not_rescore(repos):
    job = await _setup_job(repos)
    await _add_candidate(repos, job, 0.42, skills=["Python"])
    score_repo = repos[1]
    agent = _make_agent(repos)

    await agent.rank(job.id)

    scores = await score_repo.list_by_job(job.id)
    assert scores[0].similarity_score == 0.42  # untouched


async def test_audit_log_records_the_full_ordering(repos):
    job = await _setup_job(repos)
    await _add_candidate(repos, job, 0.9)
    await _add_candidate(repos, job, 0.5)
    audit_repo = repos[4]
    agent = _make_agent(repos)

    await agent.rank(job.id)

    assert len(audit_repo.created) == 1
    entry = audit_repo.created[0]
    assert entry.agent_name == "ranking"
    assert entry.input_ref == f"job:{job.id}"
    assert entry.output["total_candidates"] == 2
    assert len(entry.output["ordering"]) == 2
    # Records that no LLM was involved rather than leaving it blank.
    assert "deterministic" in entry.model_used


async def test_tied_candidates_share_a_rank(repos):
    job = await _setup_job(repos)
    await _add_candidate(repos, job, 0.7, skills=["Python"])
    await _add_candidate(repos, job, 0.7, skills=["Python"])
    score_repo = repos[1]
    agent = _make_agent(repos)

    result = await agent.rank(job.id)

    ranks = sorted(s.rank for s in await score_repo.list_by_job(job.id))
    assert ranks == [1, 1]
    assert "tied" in result.reasoning.lower()
