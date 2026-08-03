"""FeedbackAgent unit tests using in-memory fakes."""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.feedback.agent import FeedbackAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.score import Score
from app.domain.entities.skill import SkillCategory
from app.domain.feedback.recommendation import RecommendationCategory
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.feedback_repository import FeedbackRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from tests.fakes import ScriptedLLMProvider

NARRATIVE_JSON = """{
  "summary": "Solid backend candidate with strong Python experience.",
  "strengths": ["Deep Python background", "Relevant project work"],
  "weaknesses": ["No demonstrated Kubernetes experience"],
  "risk_factors": ["Required skill Kubernetes has no supporting evidence in the resume"],
  "improvement_suggestions": ["Building a Kubernetes project would strengthen future applications"]
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

    async def get_by_id(self, job_id):
        return self._jobs.get(job_id)

    async def list_all(self, skip: int = 0, limit: int = 50):
        return list(self._jobs.values())[skip : skip + limit]


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


class FakeScoreRepository(ScoreRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, Score] = {}

    async def upsert(self, score: Score) -> Score:
        self._by_resume[score.resume_id] = score
        return score

    async def get_by_resume_id(self, resume_id):
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id):
        return [s for s in self._by_resume.values() if s.job_id == job_id]

    async def update_rank(self, score_id, rank: int) -> None:
        pass


class FakeFeedbackRepository(FeedbackRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, CandidateFeedback] = {}
        self.upsert_count = 0

    async def upsert(self, feedback: CandidateFeedback) -> CandidateFeedback:
        self.upsert_count += 1
        self._by_resume[feedback.resume_id] = feedback
        return feedback

    async def get_by_resume_id(self, resume_id):
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id):
        return [f for f in self._by_resume.values() if f.job_id == job_id]


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
        FakeFeedbackRepository(),
        FakeAuditLogRepository(),
    )


def _make_agent(repos, llm):
    resume_repo, job_repo, skill_repo, score_repo, feedback_repo, audit_repo = repos
    return FeedbackAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        feedback_repository=feedback_repo,
        llm_provider=llm,
        model_name="test-model",
    )


async def _setup(
    repos, status=ResumeStatus.PARSED, with_score=True, similarity=0.85, missing=None
):
    resume_repo, job_repo, skill_repo, score_repo, _, _ = repos
    job = await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title="Backend Engineer",
            description="...",
            required_skills=["Python", "Kubernetes"],
            preferred_skills=["Go"],
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
            parsed_data={"projects": [], "experience": [], "education": []},
            created_at=datetime.now(timezone.utc),
        )
    )
    skill_repo.set_skills(resume.id, ["Python"])
    if with_score:
        await score_repo.upsert(
            Score(
                id=uuid.uuid4(),
                resume_id=resume.id,
                job_id=job.id,
                similarity_score=similarity,
                skill_overlap=["Python"],
                missing_skills=missing if missing is not None else [],
                strengths=[],
                weaknesses=[],
                rank=None,
                explanation=None,
                created_at=datetime.now(timezone.utc),
            )
        )
    return job, resume


async def test_successful_feedback_persists_recommendation_and_narrative(repos):
    _, resume = await _setup(repos, similarity=0.85)
    feedback_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    result = await agent.generate(resume.id)

    assert result.success is True
    saved = await feedback_repo.get_by_resume_id(resume.id)
    assert saved.recommendation == RecommendationCategory.STRONG_RECOMMEND
    assert saved.summary
    assert saved.improvement_suggestions


async def test_missing_score_is_a_hard_prerequisite(repos):
    # A hiring recommendation with no evidence base is precisely what the
    # design set out to prevent — unlike Phase 11, this must not proceed.
    _, resume = await _setup(repos, with_score=False)
    llm = ScriptedLLMProvider([NARRATIVE_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id)

    assert result.success is False
    assert "match score" in result.reasoning.lower()
    assert llm.call_count == 0


async def test_llm_failure_still_persists_the_recommendation(repos):
    _, resume = await _setup(repos, similarity=0.85)
    feedback_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider(["garbage", "still garbage"]))

    result = await agent.generate(resume.id)

    assert result.success is True
    saved = await feedback_repo.get_by_resume_id(resume.id)
    assert saved.recommendation == RecommendationCategory.STRONG_RECOMMEND
    assert saved.threshold_rationale  # arithmetic justification survives
    assert saved.summary is None
    assert saved.narrative_generation_failed is True


async def test_recommendation_identical_whether_llm_succeeds_or_fails(repos):
    _, resume = await _setup(repos, similarity=0.70)
    feedback_repo = repos[4]

    await _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON])).generate(resume.id)
    with_llm = (await feedback_repo.get_by_resume_id(resume.id)).recommendation

    await _make_agent(repos, ScriptedLLMProvider(["bad", "bad"])).generate(resume.id)
    without_llm = (await feedback_repo.get_by_resume_id(resume.id)).recommendation

    assert with_llm == without_llm


async def test_missing_required_skill_caps_the_recommendation(repos):
    # Kubernetes is required; Go is only preferred. Missing the required one
    # should cap the category, missing the preferred one should not.
    _, resume = await _setup(repos, similarity=0.90, missing=["Kubernetes"])
    feedback_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    await agent.generate(resume.id)

    saved = await feedback_repo.get_by_resume_id(resume.id)
    assert saved.recommendation == RecommendationCategory.RECOMMEND


async def test_missing_preferred_skill_does_not_cap_the_recommendation(repos):
    _, resume = await _setup(repos, similarity=0.90, missing=["Go"])
    feedback_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    await agent.generate(resume.id)

    saved = await feedback_repo.get_by_resume_id(resume.id)
    assert saved.recommendation == RecommendationCategory.STRONG_RECOMMEND


async def test_regenerating_replaces_rather_than_accumulating(repos):
    _, resume = await _setup(repos)
    feedback_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    await agent.generate(resume.id)
    await agent.generate(resume.id)

    assert len(await feedback_repo.list_by_job(resume.job_id)) == 1


async def test_unparsed_resume_fails_without_calling_llm(repos):
    _, resume = await _setup(repos, status=ResumeStatus.UPLOADED)
    llm = ScriptedLLMProvider([NARRATIVE_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id)

    assert result.success is False
    assert llm.call_count == 0


async def test_resume_not_found_fails_gracefully(repos):
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))
    result = await agent.generate(uuid.uuid4())
    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_output_always_includes_advisory_notice(repos):
    _, resume = await _setup(repos)
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    result = await agent.generate(resume.id)

    assert "not a hiring decision" in result.output["advisory_notice"].lower()


async def test_audit_log_records_the_recommendation_and_rationale(repos):
    _, resume = await _setup(repos, similarity=0.30)
    audit_repo = repos[5]
    agent = _make_agent(repos, ScriptedLLMProvider([NARRATIVE_JSON]))

    await agent.generate(resume.id)

    entry = audit_repo.created[0]
    assert entry.agent_name == "feedback"
    assert entry.input_ref == f"resume:{resume.id}"
    assert entry.output["recommendation"] == "not_recommended"
    # The arithmetic justification is in the permanent audit trail, so an
    # adverse recommendation can always be explained after the fact.
    assert "0.30" in entry.output["threshold_rationale"]
