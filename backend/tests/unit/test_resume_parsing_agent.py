"""
ResumeParsingAgent unit tests using hand-rolled fakes for every dependency
(LLMProvider, ResumeRepository, CandidateRepository, FileStorage,
AuditLogRepository). This is the entire payoff of the adapter pattern:
we can fully exercise retry logic, candidate resolution, and failure
handling without a real API key, database, or disk.
"""
import io
import uuid
from datetime import datetime, timezone

from reportlab.pdfgen import canvas

from app.agents.resume_parser.agent import ResumeParsingAgent
from app.domain.entities.audit_log import AuditLog
from app.domain.entities.candidate import Candidate
from app.domain.entities.resume import Resume, ResumeStatus
from app.domain.interfaces.audit_log_repository import AuditLogRepository
from app.domain.interfaces.candidate_repository import CandidateRepository
from app.domain.interfaces.file_storage import FileStorage
from app.domain.interfaces.llm_provider import LLMProvider
from app.domain.interfaces.resume_repository import ResumeRepository
from tests.fakes import ScriptedLLMProvider

VALID_JSON_RESPONSE = """{
  "full_name": "Jane Doe",
  "email": "jane.doe@example.com",
  "phone": "555-1234",
  "education": [{"institution": "MIT", "degree": "BSc", "field_of_study": "CS"}],
  "experience": [{"company": "Acme", "title": "Engineer", "description": "Built things"}],
  "projects": [],
  "skills": ["Python", "SQL"],
  "certificates": [],
  "links": {"github": "https://github.com/janedoe"}
}"""

NO_EMAIL_JSON_RESPONSE = """{
  "full_name": "Anonymous Candidate",
  "skills": ["Java"]
}"""


class FakeResumeRepository(ResumeRepository):
    def __init__(self) -> None:
        self._resumes: dict[uuid.UUID, Resume] = {}

    async def create(self, resume: Resume) -> Resume:
        self._resumes[resume.id] = resume
        return resume

    async def get_by_id(self, resume_id: uuid.UUID) -> Resume | None:
        return self._resumes.get(resume_id)

    async def update(self, resume: Resume) -> Resume:
        if resume.id not in self._resumes:
            raise ValueError("not found")
        self._resumes[resume.id] = resume
        return resume

    async def list_by_job(self, job_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Resume]:
        return [r for r in self._resumes.values() if r.job_id == job_id][skip : skip + limit]


class FakeCandidateRepository(CandidateRepository):
    def __init__(self) -> None:
        self._candidates: dict[str, Candidate] = {}  # keyed by lowercased email

    async def get_by_email(self, email: str) -> Candidate | None:
        return self._candidates.get(email.lower())

    async def get_by_id(self, candidate_id: uuid.UUID) -> Candidate | None:
        return next((c for c in self._candidates.values() if c.id == candidate_id), None)

    async def create(self, candidate: Candidate) -> Candidate:
        self._candidates[candidate.email.lower()] = candidate
        return candidate


class FakeFileStorage(FileStorage):
    def __init__(self, files: dict[str, bytes] | None = None) -> None:
        self._files = files or {}

    async def save(self, content: bytes, filename: str) -> str:
        key = str(uuid.uuid4())
        self._files[key] = content
        return key

    async def read(self, storage_path: str) -> bytes:
        return self._files[storage_path]

    async def delete(self, storage_path: str) -> None:
        self._files.pop(storage_path, None)


class FakeAuditLogRepository(AuditLogRepository):
    def __init__(self) -> None:
        self.created: list[AuditLog] = []

    async def create(self, audit_log: AuditLog) -> AuditLog:
        self.created.append(audit_log)
        return audit_log


async def _make_resume_with_pdf(resume_repo: FakeResumeRepository, file_storage: FakeFileStorage) -> Resume:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, "Jane Doe resume content")
    c.save()
    pdf_bytes = buffer.getvalue()

    storage_path = await file_storage.save(pdf_bytes, "resume.pdf")
    resume = Resume(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        storage_path=storage_path,
        original_filename="resume.pdf",
        status=ResumeStatus.UPLOADED,
        created_at=datetime.now(timezone.utc),
    )
    return await resume_repo.create(resume)


def _make_agent(llm: LLMProvider, resume_repo, candidate_repo, file_storage, audit_repo):
    return ResumeParsingAgent(
        audit_log_repository=audit_repo,
        resume_repository=resume_repo,
        candidate_repository=candidate_repo,
        file_storage=file_storage,
        llm_provider=llm,
        model_name="test-model",
    )


async def test_successful_parse_updates_resume_and_creates_candidate():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider([VALID_JSON_RESPONSE])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)

    assert result.success is True
    updated = await resume_repo.get_by_id(resume.id)
    assert updated.status == ResumeStatus.PARSED
    assert updated.parsed_data["full_name"] == "Jane Doe"
    assert updated.candidate_id is not None

    candidate = await candidate_repo.get_by_email("jane.doe@example.com")
    assert candidate is not None
    assert candidate.id == updated.candidate_id
    assert llm.call_count == 1


async def test_retry_succeeds_after_one_malformed_response():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider(["not valid json at all", VALID_JSON_RESPONSE])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)

    assert result.success is True
    assert llm.call_count == 2


async def test_markdown_fenced_json_is_handled():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    fenced = f"```json\n{VALID_JSON_RESPONSE}\n```"
    llm = ScriptedLLMProvider([fenced])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)
    assert result.success is True


async def test_both_attempts_malformed_marks_resume_failed():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider(["garbage one", "garbage two"])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)

    assert result.success is False
    updated = await resume_repo.get_by_id(resume.id)
    assert updated.status == ResumeStatus.FAILED
    assert llm.call_count == 2


async def test_missing_email_leaves_candidate_unresolved():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider([NO_EMAIL_JSON_RESPONSE])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)

    assert result.success is True
    updated = await resume_repo.get_by_id(resume.id)
    assert updated.status == ResumeStatus.PARSED
    assert updated.candidate_id is None
    assert "not resolved" in result.reasoning


async def test_existing_candidate_is_reused_case_insensitively():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    existing = Candidate(
        id=uuid.uuid4(), full_name="Jane Doe", email="Jane.Doe@Example.com",
        created_at=datetime.now(timezone.utc),
    )
    await candidate_repo.create(existing)

    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider([VALID_JSON_RESPONSE])  # email: jane.doe@example.com
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(resume.id)

    assert result.success is True
    updated = await resume_repo.get_by_id(resume.id)
    assert updated.candidate_id == existing.id  # reused, not duplicated


async def test_resume_not_found_fails_gracefully():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    llm = ScriptedLLMProvider([VALID_JSON_RESPONSE])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    result = await agent.parse(uuid.uuid4())

    assert result.success is False
    assert "not found" in result.reasoning.lower()


async def test_audit_log_is_written_on_success_and_failure():
    resume_repo, candidate_repo, storage, audit_repo = (
        FakeResumeRepository(), FakeCandidateRepository(), FakeFileStorage(), FakeAuditLogRepository(),
    )
    resume = await _make_resume_with_pdf(resume_repo, storage)
    llm = ScriptedLLMProvider([VALID_JSON_RESPONSE])
    agent = _make_agent(llm, resume_repo, candidate_repo, storage, audit_repo)

    await agent.parse(resume.id)

    assert len(audit_repo.created) == 1
    entry = audit_repo.created[0]
    assert entry.agent_name == "resume_parser"
    assert entry.input_ref == f"resume:{resume.id}"
    assert entry.model_used == "test-model"
    assert entry.output is not None
