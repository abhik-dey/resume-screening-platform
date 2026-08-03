"""
InterviewQuestionAgent unit tests using in-memory fakes.

The failure behavior gets particular attention: unlike scoring, this agent
has no deterministic fallback, so it must fail cleanly and persist nothing
rather than saving fabricated placeholder questions.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.agents.interview_question.agent import InterviewQuestionAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.interview_question import InterviewQuestion
from app.domain.entities.job import Job, JobStatus
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.entities.resume_skill import ResumeSkillDetail
from app.domain.entities.score import Score
from app.domain.entities.skill import SkillCategory
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.interview_question_repository import InterviewQuestionRepository
from app.domain.interfaces.job_repository import JobRepository
from app.domain.interfaces.resume_repository import ResumeRepository
from app.domain.interfaces.resume_skill_repository import ResumeSkillRepository
from app.domain.interfaces.score_repository import ScoreRepository
from tests.fakes import ScriptedLLMProvider

VALID_QUESTIONS_JSON = """{
  "questions": [
    {"question": "Walk me through how you'd containerize the payment service you built.",
     "category": "technical", "difficulty": "medium",
     "rationale": "Probes the Kubernetes gap found during matching."},
    {"question": "Tell me about a time you disagreed with a technical decision.",
     "category": "behavioral", "difficulty": "easy",
     "rationale": "Standard collaboration signal."},
    {"question": "What was the hardest bug in your payment service project?",
     "category": "project", "difficulty": "hard",
     "rationale": "Explores depth behind their listed project."}
  ]
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

    async def list_by_job(self, job_id, skip: int = 0, limit: int = 50) -> list[Resume]:
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

    async def upsert(self, score: Score) -> Score:
        self._by_resume[score.resume_id] = score
        return score

    async def get_by_resume_id(self, resume_id: uuid.UUID) -> Score | None:
        return self._by_resume.get(resume_id)

    async def list_by_job(self, job_id: uuid.UUID) -> list[Score]:
        return [s for s in self._by_resume.values() if s.job_id == job_id]

    async def update_rank(self, score_id: uuid.UUID, rank: int) -> None:
        for score in self._by_resume.values():
            if score.id == score_id:
                score.rank = rank
                return


class FakeInterviewQuestionRepository(InterviewQuestionRepository):
    def __init__(self) -> None:
        self._by_resume: dict[uuid.UUID, list[InterviewQuestion]] = {}
        self.replace_call_count = 0

    async def replace_for_resume(self, resume_id, questions) -> list[InterviewQuestion]:
        self.replace_call_count += 1
        self._by_resume[resume_id] = list(questions)
        return list(questions)

    async def list_by_resume(self, resume_id: uuid.UUID) -> list[InterviewQuestion]:
        return self._by_resume.get(resume_id, [])


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
        FakeInterviewQuestionRepository(),
        FakeAuditLogRepository(),
    )


def _make_agent(repos, llm):
    resume_repo, job_repo, skill_repo, score_repo, question_repo, audit_repo = repos
    return InterviewQuestionAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        resume_skill_repository=skill_repo,
        job_repository=job_repo,
        score_repository=score_repo,
        interview_question_repository=question_repo,
        llm_provider=llm,
        model_name="test-model",
    )


async def _setup(repos, status=ResumeStatus.PARSED, with_score=True, missing_skills=None):
    resume_repo, job_repo, skill_repo, score_repo, _, _ = repos
    job = await job_repo.create(
        Job(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            title="Backend Engineer",
            description="...",
            required_skills=["Python", "Kubernetes"],
            preferred_skills=[],
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
                "projects": [{"name": "Payment service", "description": "Built payments"}],
                "experience": [{"company": "Acme", "title": "Engineer"}],
            },
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
                similarity_score=0.6,
                skill_overlap=["Python"],
                missing_skills=missing_skills if missing_skills is not None else ["Kubernetes"],
                strengths=[],
                weaknesses=[],
                rank=None,
                explanation=None,
                created_at=datetime.now(timezone.utc),
            )
        )
    return job, resume


async def test_successful_generation_persists_questions(repos):
    _, resume = await _setup(repos)
    question_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    result = await agent.generate(resume.id)

    assert result.success is True
    saved = await question_repo.list_by_resume(resume.id)
    assert len(saved) == 3
    assert all(q.rationale for q in saved)  # every question justifies itself


async def test_output_summarizes_category_and_difficulty_spread(repos):
    _, resume = await _setup(repos)
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    result = await agent.generate(resume.id)

    assert result.output["by_category"] == {"technical": 1, "behavioral": 1, "project": 1}
    assert result.output["by_difficulty"] == {"medium": 1, "easy": 1, "hard": 1}


async def test_llm_failure_persists_nothing(repos):
    # No deterministic fallback exists for a creative task — failing cleanly
    # beats saving fabricated filler a recruiter might mistake for analysis.
    _, resume = await _setup(repos)
    question_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider(["garbage", "still garbage"]))

    result = await agent.generate(resume.id)

    assert result.success is False
    assert await question_repo.list_by_resume(resume.id) == []
    assert question_repo.replace_call_count == 0


async def test_empty_question_list_treated_as_failure(repos):
    _, resume = await _setup(repos)
    question_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider(['{"questions": []}']))

    result = await agent.generate(resume.id)

    assert result.success is False
    assert question_repo.replace_call_count == 0


async def test_regenerating_replaces_rather_than_appends(repos):
    _, resume = await _setup(repos)
    question_repo = repos[4]
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    await agent.generate(resume.id)
    await agent.generate(resume.id)

    saved = await question_repo.list_by_resume(resume.id)
    assert len(saved) == 3  # not 6


async def test_missing_skills_are_passed_to_the_prompt(repos):
    _, resume = await _setup(repos, missing_skills=["Kubernetes", "Terraform"])
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    result = await agent.generate(resume.id)

    assert result.output["grounded_in_missing_skills"] == ["Kubernetes", "Terraform"]


async def test_generation_works_without_a_match_score(repos):
    # Matching is useful context but shouldn't be a hard prerequisite —
    # a recruiter may want questions before running the match.
    _, resume = await _setup(repos, with_score=False)
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    result = await agent.generate(resume.id)

    assert result.success is True
    assert result.output["grounded_in_missing_skills"] == []
    assert "no match score" in result.reasoning.lower()


async def test_unparsed_resume_fails_without_calling_llm(repos):
    _, resume = await _setup(repos, status=ResumeStatus.UPLOADED)
    llm = ScriptedLLMProvider([VALID_QUESTIONS_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id)

    assert result.success is False
    assert "must be parsed" in result.reasoning.lower()
    assert llm.call_count == 0  # don't waste an API call


async def test_resume_not_found_fails_gracefully(repos):
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))
    result = await agent.generate(uuid.uuid4())
    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_invalid_question_count_rejected_before_llm_call(repos):
    _, resume = await _setup(repos)
    llm = ScriptedLLMProvider([VALID_QUESTIONS_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id, question_count=500)

    assert result.success is False
    assert "question_count" in result.reasoning
    assert llm.call_count == 0


async def test_invalid_category_in_llm_output_triggers_retry(repos):
    _, resume = await _setup(repos)
    bad = '{"questions": [{"question": "Q", "category": "not_a_category", ' \
          '"difficulty": "easy", "rationale": "R"}]}'
    llm = ScriptedLLMProvider([bad, VALID_QUESTIONS_JSON])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id)

    assert result.success is True
    assert llm.call_count == 2  # schema validation caught the bad enum value


async def test_question_missing_rationale_is_rejected(repos):
    # rationale is required — a question without one is generic, which
    # defeats the purpose of tailoring questions to a candidate.
    _, resume = await _setup(repos)
    no_rationale = '{"questions": [{"question": "Q", "category": "technical", "difficulty": "easy"}]}'
    llm = ScriptedLLMProvider([no_rationale, no_rationale])
    agent = _make_agent(repos, llm)

    result = await agent.generate(resume.id)

    assert result.success is False


async def test_audit_log_records_generation(repos):
    _, resume = await _setup(repos)
    audit_repo = repos[5]
    agent = _make_agent(repos, ScriptedLLMProvider([VALID_QUESTIONS_JSON]))

    await agent.generate(resume.id)

    assert len(audit_repo.created) == 1
    entry = audit_repo.created[0]
    assert entry.agent_name == "interview_question"
    assert entry.input_ref == f"resume:{resume.id}"
    assert len(entry.output["questions"]) == 3
