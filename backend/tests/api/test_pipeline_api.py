"""API-level tests for pipeline orchestration."""
import io

from app.api.deps import get_llm_provider_dependency
from app.main import app
from tests.fakes import VALID_PARSED_RESUME_JSON, ScriptedLLMProvider


def _build_pdf(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, text)
    c.save()
    return buffer.getvalue()


async def _register_and_login(client, email: str, role: str | None = None):
    payload = {"email": email, "password": "supersecret1", "full_name": "Test User"}
    if role:
        payload["role"] = role
    await client.post("/api/v1/auth/register", json=payload)
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def _create_job_with_resume(client, token):
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Build APIs.", "required_skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("Jane Doe resume"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    return job_id, upload.json()["id"]


class MultiResponseLLM(ScriptedLLMProvider):
    """Returns a schema-appropriate response for each agent in turn.

    The pipeline calls several agents with different output schemas, so a
    single canned response can't satisfy all of them.
    """

    def __init__(self) -> None:
        super().__init__([VALID_PARSED_RESUME_JSON])
        self._responses = [
            VALID_PARSED_RESUME_JSON,  # parse
            '{"skills": []}',  # skill extraction (all dictionary hits anyway)
            '{"strengths": ["Python"], "weaknesses": []}',  # matching
            '{"questions": [{"question": "Q?", "category": "technical", '
            '"difficulty": "easy", "rationale": "R"}]}',  # interview questions
            '{"summary": "S", "strengths": [], "weaknesses": [], '
            '"risk_factors": [], "improvement_suggestions": []}',  # feedback
            '{"summary": "Report summary."}',  # report
        ]
        self._index = 0

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return response


def _use_pipeline_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: MultiResponseLLM()


def _restore_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [VALID_PARSED_RESUME_JSON]
    )


async def test_describe_pipeline_endpoint(client):
    token = await _register_and_login(client, "pipe1@company.com")
    resp = await client.get(
        "/api/v1/pipeline/describe", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [s["name"] for s in body["steps"]][0] == "parse"
    assert body["fatal_step_policy"]


async def test_resume_pipeline_runs_all_steps(client):
    token = await _register_and_login(client, "pipe2@company.com")
    _, resume_id = await _create_job_with_resume(client, token)

    _use_pipeline_llm()
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/pipeline", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["halted"] is False
    assert "parse" in body["completed_steps"]
    assert "match" in body["completed_steps"]
    assert "feedback" in body["completed_steps"]


async def test_resume_pipeline_halts_on_parse_failure(client):
    token = await _register_and_login(client, "pipe3@company.com")
    _, resume_id = await _create_job_with_resume(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        ["garbage", "still garbage"]
    )
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/pipeline", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        _restore_llm()

    body = resp.json()
    assert body["success"] is False
    assert body["halted"] is True
    assert "parse" in body["failed_steps"]
    assert body["completed_steps"] == []
    assert "parse" in body["halt_reason"]


async def test_resume_pipeline_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "pipe4@company.com")
    resp = await client.post(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000/pipeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_run_pipeline(client):
    admin_token = await _register_and_login(client, "pipe5@company.com")
    _, resume_id = await _create_job_with_resume(client, admin_token)
    viewer_token = await _register_and_login(client, "pipeviewer@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/pipeline", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_job_pipeline_processes_all_resumes_then_ranks_and_reports(client):
    token = await _register_and_login(client, "pipe6@company.com")
    job_id, _ = await _create_job_with_resume(client, token)
    # A second resume, so ranking has something comparative to do.
    await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r2.pdf", _build_pdf("Second candidate"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )

    _use_pipeline_llm()
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/pipeline", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_resumes"] == 2
    assert len(body["resume_results"]) == 2
    assert body["ranking_success"] is True
    assert body["report_success"] is True
    assert body["report_id"]


async def test_job_pipeline_can_skip_the_report(client):
    token = await _register_and_login(client, "pipe7@company.com")
    job_id, _ = await _create_job_with_resume(client, token)

    _use_pipeline_llm()
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/pipeline?generate_report=false",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    body = resp.json()
    assert body["ranking_success"] is True
    assert body["report_success"] is False
    assert body["report_id"] is None


async def test_job_pipeline_with_no_resumes_returns_404(client):
    token = await _register_and_login(client, "pipe8@company.com")
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Empty", "description": "No applicants."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/pipeline", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404
    assert "no resumes" in resp.json()["detail"].lower()


async def test_job_pipeline_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "pipe9@company.com")
    resp = await client.post(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/pipeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
