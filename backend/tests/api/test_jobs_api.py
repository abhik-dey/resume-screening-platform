"""API-level tests for /api/v1/jobs/*."""


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
