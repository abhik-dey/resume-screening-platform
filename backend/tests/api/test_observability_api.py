"""API-level observability tests: middleware, /metrics, and real instrumentation."""
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


async def _register_and_login(client, email: str):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Test User"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_metrics_endpoint_is_reachable(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "# HELP" in resp.text


async def test_metrics_endpoint_needs_no_auth(client):
    # Prometheus scrapers don't carry bearer tokens. Access control for
    # this endpoint is a network concern, not an application one.
    resp = await client.get("/metrics")
    assert resp.status_code == 200


async def test_request_id_is_returned_in_the_response(client):
    resp = await client.get("/api/v1/pipeline/describe")
    assert "x-request-id" in {k.lower() for k in resp.headers}


async def test_inbound_request_id_is_honored(client):
    # Preserving an inbound ID keeps the trail intact across services.
    resp = await client.get(
        "/api/v1/pipeline/describe", headers={"X-Request-ID": "trace-me-123"}
    )
    assert resp.headers["x-request-id"] == "trace-me-123"


async def test_each_request_gets_a_distinct_id(client):
    first = await client.get("/api/v1/pipeline/describe")
    second = await client.get("/api/v1/pipeline/describe")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_http_metrics_record_the_route_template_not_the_raw_path(client):
    # /api/v1/jobs/{job_id} rather than the concrete UUID — otherwise every
    # ID becomes its own label value and Prometheus cardinality explodes.
    token = await _register_and_login(client, "obs1@company.com")
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Engineer", "description": "Build."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    await client.get(f"/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})

    metrics = (await client.get("/metrics")).text
    assert "{job_id}" in metrics
    assert job_id not in metrics


async def test_failed_requests_are_recorded_with_their_status(client):
    await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    metrics = (await client.get("/metrics")).text
    assert 'status="401"' in metrics or 'status="404"' in metrics


async def test_agent_execution_populates_agent_metrics(client):
    # The metric that matters most: which agent is slow and expensive.
    token = await _register_and_login(client, "obs2@company.com")
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Engineer", "description": "Build."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("Jane Doe resume"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]
    await client.post(
        f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
    )

    metrics = (await client.get("/metrics")).text
    assert 'agent_runs_total{agent="resume_parser",outcome="success"}' in metrics
    assert 'agent_duration_seconds_count{agent="resume_parser"}' in metrics


async def test_agent_failures_are_recorded_as_failures(client):
    token = await _register_and_login(client, "obs3@company.com")
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Engineer", "description": "Build."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        ["garbage", "still garbage"]
    )
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    metrics = (await client.get("/metrics")).text
    assert 'agent_runs_total{agent="resume_parser",outcome="failure"}' in metrics


async def test_llm_retries_are_recorded_when_output_is_malformed(client):
    # Retries are otherwise silent — this is how provider degradation
    # becomes visible before users complain.
    token = await _register_and_login(client, "obs4@company.com")
    job = await client.post(
        "/api/v1/jobs",
        json={"title": "Engineer", "description": "Build."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        ["not json", VALID_PARSED_RESUME_JSON]
    )
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    metrics = (await client.get("/metrics")).text
    assert "llm_retries_total" in metrics
    assert 'llm_calls_total{outcome="malformed"' in metrics
