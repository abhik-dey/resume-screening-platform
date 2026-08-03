"""ReportGeneratorAgent unit tests using in-memory fakes."""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.report.agent import ReportGeneratorAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.candidate import Candidate
from app.domain.entities.candidate_feedback import CandidateFeedback
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.report import Report
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.score import Score
from app.domain.feedback.recommendation import RecommendationCategory
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.feedback_repository import FeedbackRepository
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.report_repository import ReportRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.score_repository import ScoreRepository
from tests.fakes import ScriptedLLMProvider

SUMMARY_JSON = '{"summary": "Two candidates screened, one strong match identified."}'


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


class FakeCandidateRepository(CandidateRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Candidate] = {}

    async def get_by_email(self, email: str):
        return next((c for c in self._by_id.values() if c.email.lower() == email.lower()), None)

    async def get_by_id(self, candidate_id):
        return self._by_id.get(candidate_id)

    async def create(self, candidate: Candidate) -> Candidate:
        self._by_id[candidate.id] = candidate
        return candidate


class FakeFeedbackRepository(FeedbackRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, CandidateFeedback] = {}

    async def upsert(self, feedback: CandidateFeedback) -> CandidateFeedback:
        self._by_resume[feedback.resume_id] = feedback
        return feedback

    async def get_by_resume_id(self, resume_id):
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id):
        return [f for f in self._by_resume.values() if f.job_id == job_id]


class FakeReportRepository(ReportRepository):
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, Report] = {}

    async def create(self, report: Report) -> Report:
        self._by_id[report.id] = report
        return report

    async def get_by_id(self, report_id):
        return self._by_id.get(report_id)

    async def list_by_job(self, job_id):
        return [r for r in self._by_id.values() if r.job_id == job_id]


class FakeFileStorage(FileStorage):
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, content: bytes, filename: str) -> str:
        key = f"{uuid.uuid4()}-{filename}"
        self.files[key] = content
        return key

    async def read(self, storage_path: str) -> bytes:
        return self.files[storage_path]

    async def delete(self, storage_path: str) -> None:
        self.files.pop(storage_path, None)


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
        FakeCandidateRepository(),
        FakeFeedbackRepository(),
        FakeReportRepository(),
        FakeFileStorage(),
        FakeAuditLogRepository(),
    )


def _make_agent(repos, llm):
    job_repo, score_repo, resume_repo, cand_repo, feedback_repo, report_repo, storage, audit_repo = repos
    return ReportGeneratorAgent(
        audit_log_repository=audit_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        resume_repository=resume_repo,
        candidate_repository=cand_repo,
        feedback_repository=feedback_repo,
        report_repository=report_repo,
        file_storage=storage,
        llm_provider=llm,
        model_name="test-model",
    )


async def _setup(repos, candidate_count=2, with_feedback=True):
    job_repo, score_repo, resume_repo, cand_repo, feedback_repo, _, _, _ = repos
    job = await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title="Backend Engineer",
            description="Build APIs.",
            required_skills=["Python", "SQL"],
            preferred_skills=[],
            status=JobStatus.OPEN,
            created_at=datetime.now(timezone.utc),
        )
    )
    for i in range(candidate_count):
        candidate = await cand_repo.create(
            Candidate(
                id=uuid.uuid4(),
                full_name=f"Candidate {i}",
                email=f"c{i}@example.com",
                created_at=datetime.now(timezone.utc),
            )
        )
        resume = await resume_repo.create(
            Resume(
                id=uuid.uuid4(),
                job_id=job.id,
                uploaded_by=uuid.uuid4(),
                candidate_id=candidate.id,
                storage_path=f"r{i}.pdf",
                original_filename=f"resume{i}.pdf",
                status=ResumeStatus.PARSED,
                created_at=datetime.now(timezone.utc),
            )
        )
        await score_repo.upsert(
            Score(
                id=uuid.uuid4(),
                resume_id=resume.id,
                job_id=job.id,
                similarity_score=0.9 - (i * 0.3),
                skill_overlap=["Python"],
                missing_skills=[],
                strengths=[],
                weaknesses=[],
                rank=i + 1,
                explanation=None,
                created_at=datetime.now(timezone.utc),
            )
        )
        if with_feedback:
            await feedback_repo.upsert(
                CandidateFeedback(
                    id=uuid.uuid4(),
                    resume_id=resume.id,
                    job_id=job.id,
                    recommendation=RecommendationCategory.RECOMMEND,
                    threshold_rationale="Rationale.",
                    summary="Summary text.",
                    created_at=datetime.now(timezone.utc),
                )
            )
    return job


async def test_successful_report_generation(repos):
    job = await _setup(repos)
    storage, report_repo = repos[6], repos[5]
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))

    result = await agent.generate(job.id, generated_by=uuid.uuid4(), generated_by_email="rec@co.com")

    assert result.success is True
    assert result.output["total_candidates"] == 2
    # A real PDF was written to storage.
    assert len(storage.files) == 1
    pdf_bytes = list(storage.files.values())[0]
    assert pdf_bytes[:4] == b"%PDF"
    assert len(await report_repo.list_by_job(job.id)) == 1


async def test_llm_failure_still_produces_the_report(repos):
    # Every number in the report comes from the database; the summary is
    # the only LLM contribution, so its failure can't invalidate anything.
    job = await _setup(repos)
    storage = repos[6]
    agent = _make_agent(repos, ScriptedLLMProvider(["garbage", "still garbage"]))

    result = await agent.generate(job.id, generated_by=uuid.uuid4())

    assert result.success is True
    assert result.output["summary_generation_failed"] is True
    assert len(storage.files) == 1
    assert list(storage.files.values())[0][:4] == b"%PDF"


async def test_job_with_no_scored_candidates_fails_clearly(repos):
    job = await _setup(repos, candidate_count=0)
    llm = ScriptedLLMProvider([SUMMARY_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(job.id, generated_by=uuid.uuid4())

    assert result.success is False
    assert "no scored candidates" in result.reasoning.lower()
    assert llm.call_count == 0  # don't burn an API call on an empty report


async def test_job_not_found_fails_gracefully(repos):
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))
    result = await agent.generate(uuid.uuid4(), generated_by=uuid.uuid4())
    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_candidates_without_feedback_are_included(repos):
    job = await _setup(repos, candidate_count=2, with_feedback=False)
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))

    result = await agent.generate(job.id, generated_by=uuid.uuid4())

    assert result.success is True
    assert result.output["total_candidates"] == 2
    assert result.output["recommendation_counts"] == {}


async def test_report_record_links_to_stored_file(repos):
    job = await _setup(repos)
    storage, report_repo = repos[6], repos[5]
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))

    await agent.generate(job.id, generated_by=uuid.uuid4())

    report = (await report_repo.list_by_job(job.id))[0]
    assert report.file_path in storage.files
    assert report.summary == "Two candidates screened, one strong match identified."


async def test_multiple_reports_accumulate_as_point_in_time_snapshots(repos):
    # Unlike scores/feedback, reports aren't upserted — an older report
    # describes the pool as it was then and stays valid.
    job = await _setup(repos)
    report_repo = repos[5]
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))

    await agent.generate(job.id, generated_by=uuid.uuid4())
    await agent.generate(job.id, generated_by=uuid.uuid4())

    assert len(await report_repo.list_by_job(job.id)) == 2


async def test_audit_log_records_generation(repos):
    job = await _setup(repos)
    audit_repo = repos[7]
    agent = _make_agent(repos, ScriptedLLMProvider([SUMMARY_JSON]))

    await agent.generate(job.id, generated_by=uuid.uuid4())

    entry = audit_repo.created[0]
    assert entry.agent_name == "report_generator"
    assert entry.input_ref == f"job:{job.id}"
    assert entry.output["total_candidates"] == 2
    assert entry.output["pdf_size_bytes"] > 0
