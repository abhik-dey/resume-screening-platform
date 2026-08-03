"""API-level tests for /api/v1/jobs/*."""
from app.api.deps import get_llm_provider_dependency
from app.main import app
from tests.fakes import VALID_PARSED_RESUME_JSON, ScriptedLLMProvider

JOB_EXTRACTION_JSON = """{
  "required_skills": ["python", "postgres"],
  "preferred_skills": ["k8s"],
  "min_experience_years": 5,
  "education_requirement": "BSc in Computer Science",
  "responsibilities": ["Design APIs"],
  "keywords": ["backend"]
}"""


def _use_job_extraction_llm():
    """The default fake LLM (conftest) returns parsed-resume JSON, which
    isn't valid for job analysis — swap it for this test's duration."""
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [JOB_EXTRACTION_JSON]
    )


def _restore_default_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [VALID_PARSED_RESUME_JSON]
    )


async def _register_and_login(client, email: str, role: str | None = None):
    payload = {"email": email, "password": "supersecret1", "full_name": "Test User"}
    if role:
        payload["role"] = role
    await client.post("/api/v1/auth/register", json=payload)
    login_resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login_resp.json()["access_token"]


async def test_first_user_admin_can_create_job(client):
    # First registered user becomes admin (Phase 3 bootstrap rule).
    token = await _register_and_login(client, "admin@company.com")
    resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Build APIs.", "required_skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Backend Engineer"
    assert body["status"] == "open"


async def test_viewer_cannot_create_job(client):
    await _register_and_login(client, "admin2@company.com")  # bootstrap admin first
    viewer_token = await _register_and_login(client, "viewer@company.com", role="viewer")
    resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Some Role", "description": "..."},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


async def test_list_and_get_job(client):
    token = await _register_and_login(client, "admin3@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Data Engineer", "description": "..."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_resp.json()["id"]

    list_resp = await client.get("/api/v1/jobs", headers={"Authorization": f"Bearer {token}"})
    assert list_resp.status_code == 200
    assert any(j["id"] == job_id for j in list_resp.json())

    get_resp = await client.get(f"/api/v1/jobs/{job_id}", headers={"Authorization": f"Bearer {token}"})
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == job_id


async def test_get_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "admin4@company.com")
    resp = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_analyze_job_fills_empty_fields(client):
    token = await _register_and_login(client, "admin9@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "description": "We need Python and Postgres experience. 5+ years required.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_resp.json()["id"]

    _use_job_extraction_llm()
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/analyze", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        _restore_default_llm()

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["job"]["required_skills"] == ["Python", "PostgreSQL"]
    assert body["job"]["min_experience_years"] == 5
    assert "required_skills" in body["applied_fields"]


async def test_analyze_job_preserves_recruiter_input_by_default(client):
    token = await _register_and_login(client, "admin10@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "description": "We need Python and Postgres. 5+ years.",
            "required_skills": ["Go", "Rust"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_resp.json()["id"]

    _use_job_extraction_llm()
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/analyze", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        _restore_default_llm()

    body = resp.json()
    assert body["job"]["required_skills"] == ["Go", "Rust"]  # untouched
    assert "required_skills" in body["skipped_fields"]
    # But the suggestion is still visible to the recruiter.
    assert body["extracted"]["required_skills"] == ["Python", "PostgreSQL"]


async def test_analyze_job_with_overwrite_replaces_recruiter_input(client):
    token = await _register_and_login(client, "admin11@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "description": "We need Python and Postgres. 5+ years.",
            "required_skills": ["Go", "Rust"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_resp.json()["id"]

    _use_job_extraction_llm()
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/analyze?overwrite=true",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_default_llm()

    body = resp.json()
    assert body["job"]["required_skills"] == ["Python", "PostgreSQL"]
    assert body["skipped_fields"] == []


async def test_analyze_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "admin12@company.com")
    resp = await client.post(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/analyze",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_analyze_job(client):
    admin_token = await _register_and_login(client, "admin13@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Python needed."},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    job_id = create_resp.json()["id"]
    viewer_token = await _register_and_login(client, "viewer6@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/analyze", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403
