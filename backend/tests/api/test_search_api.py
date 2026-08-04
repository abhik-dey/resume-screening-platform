"""API-level tests for indexing and semantic search."""
import io


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


async def _prepare_indexed_resume(client, token):
    job_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Build APIs.", "required_skills": ["Python"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job_resp.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("Jane Doe resume"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})
    await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    return job_id, resume_id


async def test_index_resume_succeeds(client):
    token = await _register_and_login(client, "search1@company.com")
    _, resume_id = await _prepare_indexed_resume(client, token)

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dimensions"] > 0
    assert body["embedding_model"]


async def test_index_unparsed_resume_is_a_handled_failure(client):
    token = await _register_and_login(client, "search2@company.com")
    job_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Role", "description": "Desc."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job_resp.json()["id"]
    upload = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("r.pdf", _build_pdf("content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload.json()["id"]

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


async def test_index_job_succeeds(client):
    token = await _register_and_login(client, "search3@company.com")
    job_id, _ = await _prepare_indexed_resume(client, token)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/index", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_viewer_cannot_index(client):
    admin_token = await _register_and_login(client, "search4@company.com")
    _, resume_id = await _prepare_indexed_resume(client, admin_token)
    viewer_token = await _register_and_login(client, "searchviewer1@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_search_returns_indexed_resume_with_candidate_details(client):
    token = await _register_and_login(client, "search5@company.com")
    _, resume_id = await _prepare_indexed_resume(client, token)
    await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {token}"}
    )

    resp = await client.post(
        "/api/v1/search/resumes",
        json={"query": "Python SQL backend"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hits"] >= 1
    hit = body["results"][0]
    assert hit["resume_id"] == resume_id
    # Bare vector IDs aren't actionable; the response joins in who they are.
    assert hit["candidate_name"] == "Jane Doe"
    assert 0.0 <= hit["similarity"] <= 1.0


async def test_search_response_discloses_the_embedding_model(client):
    # Callers must be able to tell whether results came from a real
    # semantic model or the non-semantic local fallback.
    token = await _register_and_login(client, "search6@company.com")
    resp = await client.post(
        "/api/v1/search/resumes",
        json={"query": "anything"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["embedding_model"]


async def test_empty_query_rejected_by_schema(client):
    token = await _register_and_login(client, "search7@company.com")
    resp = await client.post(
        "/api/v1/search/resumes", json={"query": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422


async def test_search_limit_out_of_range_rejected(client):
    token = await _register_and_login(client, "search8@company.com")
    resp = await client.post(
        "/api/v1/search/resumes",
        json={"query": "python", "limit": 5000},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_viewer_can_search(client):
    # Search is read-only discovery — exactly what the viewer role is for.
    admin_token = await _register_and_login(client, "search9@company.com")
    _, resume_id = await _prepare_indexed_resume(client, admin_token)
    await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {admin_token}"}
    )
    viewer_token = await _register_and_login(client, "searchviewer2@company.com", role="viewer")

    resp = await client.post(
        "/api/v1/search/resumes",
        json={"query": "Python"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200


async def test_similar_candidates_endpoint(client):
    token = await _register_and_login(client, "search10@company.com")
    job_id, resume_id = await _prepare_indexed_resume(client, token)
    await client.post(
        f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {token}"}
    )

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/similar-candidates", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["total_hits"] >= 1


async def test_similar_candidates_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "search11@company.com")
    resp = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/similar-candidates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_search_unauthenticated_is_rejected(client):
    resp = await client.post("/api/v1/search/resumes", json={"query": "python"})
    assert resp.status_code == 401
