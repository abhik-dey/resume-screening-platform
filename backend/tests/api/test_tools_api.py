"""API-level tests for tool listing and invocation."""


async def _register_and_login(client, email: str, role: str | None = None):
    payload = {"email": email, "password": "supersecret1", "full_name": "Test User"}
    if role:
        payload["role"] = role
    await client.post("/api/v1/auth/register", json=payload)
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login.json()["access_token"]


async def test_list_tools_returns_schemas(client):
    token = await _register_and_login(client, "tool1@company.com")
    resp = await client.get("/api/v1/tools", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    names = {t["name"] for t in body["tools"]}
    assert "resume_search" in names
    assert "email_draft" in names
    for tool in body["tools"]:
        # Self-describing is the point: an LLM consumer needs the schema.
        assert "properties" in tool["input_schema"]
        assert tool["description"]


async def test_tool_list_is_filtered_by_role(client):
    await _register_and_login(client, "tool2@company.com")  # bootstrap admin
    viewer_token = await _register_and_login(client, "toolviewer@company.com", role="viewer")

    resp = await client.get("/api/v1/tools", headers={"Authorization": f"Bearer {viewer_token}"})
    names = {t["name"] for t in resp.json()["tools"]}

    # Viewers get read-only tools, not recruiter-level ones.
    assert "resume_search" in names
    assert "database_search" in names
    assert "email_draft" not in names
    assert "filesystem_read" not in names


async def test_invoke_database_search(client):
    token = await _register_and_login(client, "tool3@company.com")
    await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Build APIs."},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.post(
        "/api/v1/tools/database_search/invoke",
        json={"params": {"query_type": "list_jobs"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]["jobs"]) >= 1


async def test_invoke_email_draft_reports_not_sent(client):
    token = await _register_and_login(client, "tool4@company.com")
    resp = await client.post(
        "/api/v1/tools/email_draft/invoke",
        json={
            "params": {
                "recipient_name": "Jane Doe",
                "subject": "Interview",
                "body": "Hello Jane",
            }
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["sent"] is False
    assert "NOT been sent" in body["notice"]


async def test_unknown_tool_returns_404(client):
    token = await _register_and_login(client, "tool5@company.com")
    resp = await client.post(
        "/api/v1/tools/nonexistent_tool/invoke",
        json={"params": {}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_insufficient_role_returns_403(client):
    await _register_and_login(client, "tool6@company.com")
    viewer_token = await _register_and_login(client, "toolviewer2@company.com", role="viewer")

    resp = await client.post(
        "/api/v1/tools/email_draft/invoke",
        json={"params": {"recipient_name": "X", "subject": "Y", "body": "Z"}},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


async def test_invalid_params_return_422(client):
    token = await _register_and_login(client, "tool7@company.com")
    resp = await client.post(
        "/api/v1/tools/resume_search/invoke",
        json={"params": {}},  # missing required 'query'
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
    assert "query" in resp.json()["detail"]


async def test_unknown_param_returns_422(client):
    token = await _register_and_login(client, "tool8@company.com")
    resp = await client.post(
        "/api/v1/tools/resume_search/invoke",
        json={"params": {"query": "python", "typo_field": 1}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_out_of_range_param_returns_422(client):
    token = await _register_and_login(client, "tool9@company.com")
    resp = await client.post(
        "/api/v1/tools/resume_search/invoke",
        json={"params": {"query": "python", "limit": 9999}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_filesystem_traversal_returns_a_failed_result_not_a_crash(client):
    # The security-critical path: a traversal attempt must be a clean,
    # contained refusal.
    token = await _register_and_login(client, "tool10@company.com")
    resp = await client.post(
        "/api/v1/tools/filesystem_read/invoke",
        json={"params": {"path": "../../../etc/passwd"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "escapes" in body["error"] or "Absolute" in body["error"]


async def test_github_tool_is_disabled_by_default(client):
    token = await _register_and_login(client, "tool11@company.com")
    resp = await client.post(
        "/api/v1/tools/github_profile/invoke",
        json={"params": {"username": "octocat"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    assert body["success"] is False
    assert "disabled" in body["error"].lower()


async def test_linkedin_tool_discloses_it_is_mocked(client):
    token = await _register_and_login(client, "tool12@company.com")
    resp = await client.post(
        "/api/v1/tools/linkedin_profile/invoke",
        json={"params": {"profile_url": "https://linkedin.com/in/x"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = resp.json()
    assert body["data"]["mock"] is True
    assert "Terms of Service" in body["notice"]


async def test_unauthenticated_tool_access_is_rejected(client):
    resp = await client.get("/api/v1/tools")
    assert resp.status_code == 401
