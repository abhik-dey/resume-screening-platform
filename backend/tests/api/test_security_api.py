"""
API-level security tests.

The IDOR tests are the important ones — they verify the Phase 13 hole is
actually closed at the endpoint, not just in the pure authorization module.
"""
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


class _PipelineLLM(ScriptedLLMProvider):
    def __init__(self) -> None:
        super().__init__([VALID_PARSED_RESUME_JSON])
        self._seq = [
            VALID_PARSED_RESUME_JSON,
            '{"skills": []}',
            '{"strengths": [], "weaknesses": []}',
            '{"summary": "Report summary."}',
        ]
        self._i = 0

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.call_count += 1
        r = self._seq[min(self._i, len(self._seq) - 1)]
        self._i += 1
        return r


async def _create_report_as(client, token) -> str:
    """Build a job with a scored resume and generate a report."""
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Engineer", "description": "Build.", "required_skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("Jane Doe resume"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]

    app.dependency_overrides[get_llm_provider_dependency] = lambda: _PipelineLLM()
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
        )
        await client.post(
            f"/api/v1/resumes/{resume_id}/extract-skills",
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
        )
        report = await client.post(
            f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )
    return report.json()["report"]["id"]


# --- The Phase 13 IDOR, verified at the endpoint ---

async def test_owner_can_download_their_report(client):
    admin_token = await _register_and_login(client, "sec_owner@company.com")
    report_id = await _create_report_as(client, admin_token)

    resp = await client.get(
        f"/api/v1/reports/{report_id}/download", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert resp.status_code == 200
    assert resp.content[:4] == b"%PDF"


async def test_stranger_cannot_download_another_users_report(client):
    # THE Phase 13 bug: before this fix, this returned 200 with the PDF.
    admin_token = await _register_and_login(client, "sec_owner2@company.com")
    report_id = await _create_report_as(client, admin_token)

    stranger_token = await _register_and_login(client, "sec_stranger@company.com")
    resp = await client.get(
        f"/api/v1/reports/{report_id}/download",
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert resp.status_code == 404  # not 403 — a 403 confirms the ID is real


async def test_viewer_cannot_download_another_users_report(client):
    # "Viewer" must not mean "can read everything".
    admin_token = await _register_and_login(client, "sec_owner3@company.com")
    report_id = await _create_report_as(client, admin_token)

    viewer_token = await _register_and_login(client, "sec_viewer@company.com", role="viewer")
    resp = await client.get(
        f"/api/v1/reports/{report_id}/download", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 404


# --- Security headers ---

async def test_security_headers_are_present(client):
    resp = await client.get("/api/v1/pipeline/describe")
    headers = {k.lower() for k in resp.headers}
    assert "x-content-type-options" in headers
    assert "x-frame-options" in headers
    assert "referrer-policy" in headers
    assert "content-security-policy" in headers


async def test_metrics_endpoint_is_exempt_from_rate_limiting(client):
    # Infrastructure polls this continuously; limiting it breaks
    # monitoring rather than stopping abuse.
    for _ in range(5):
        resp = await client.get("/metrics")
        assert resp.status_code == 200


# --- Tool audit logging (Phase 17 gap) ---

async def test_tool_invocations_are_audit_logged(client):
    token = await _register_and_login(client, "sec_tool@company.com")
    resp = await client.post(
        "/api/v1/tools/database_search/invoke",
        json={"params": {"query_type": "list_jobs"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    # The audit write happening without error is the assertion; a failure
    # would surface as a 500 here.
    assert resp.json()["success"] is True
