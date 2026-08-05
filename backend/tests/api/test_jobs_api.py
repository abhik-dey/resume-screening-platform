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


MATCH_ANALYSIS_JSON = """{
  "strengths": ["Strong Python background"],
  "weaknesses": ["Limited cloud exposure"]
}"""


def _build_pdf(text: str) -> bytes:
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(72, 720, text)
    c.save()
    return buffer.getvalue()


async def _prepare_scored_job(client, token, required_skills=None, candidate_count=2):
    """Create a job, then upload/parse/extract/match N resumes against it."""
    job_resp = await client.post(
        "/api/v1/jobs",
        json={
            "title": "Backend Engineer",
            "description": "Build APIs.",
            "required_skills": required_skills if required_skills is not None else ["Python", "SQL"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job_resp.json()["id"]

    resume_ids = []
    for i in range(candidate_count):
        upload_resp = await client.post(
            f"/api/v1/jobs/{job_id}/resumes",
            files={"file": (f"resume{i}.pdf", _build_pdf(f"Candidate {i} resume"), "application/pdf")},
            headers={"Authorization": f"Bearer {token}"},
        )
        resume_id = upload_resp.json()["id"]
        resume_ids.append(resume_id)
        await client.post(
            f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
        )
        await client.post(
            f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
        )
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [MATCH_ANALYSIS_JSON]
        )
        try:
            await client.post(
                f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
            )
        finally:
            app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
                [VALID_PARSED_RESUME_JSON]
            )
    return job_id, resume_ids


async def test_rank_assigns_ranks_to_all_candidates(client):
    token = await _register_and_login(client, "recruiter30@company.com")
    job_id, resume_ids = await _prepare_scored_job(client, token, candidate_count=3)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total_candidates"] == 3
    assert len(body["ranking"]) == 3
    # All candidates here are identical, so competition ranking gives them
    # all rank 1 rather than inventing an order.
    assert all(c["rank"] == 1 for c in body["ranking"])


async def test_rank_is_deterministic_across_calls(client):
    token = await _register_and_login(client, "recruiter31@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=3)

    orderings = []
    for _ in range(3):
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {token}"}
        )
        orderings.append([c["resume_id"] for c in resp.json()["ranking"]])

    assert orderings[0] == orderings[1] == orderings[2]


async def test_rank_with_custom_weights(client):
    token = await _register_and_login(client, "recruiter32@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=2)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank",
        json={"weights": {"skills": 0.8, "experience": 0.1, "education": 0.1}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["weights_applied"]["skills"] == 0.8


async def test_rank_rejects_weights_that_do_not_sum_to_one(client):
    token = await _register_and_login(client, "recruiter33@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=1)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank",
        json={"weights": {"skills": 0.5, "experience": 0.5, "education": 0.5}},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Caught by schema validation, so the recruiter gets a clear 422 rather
    # than a vague agent failure.
    assert resp.status_code == 422


async def test_rank_rejects_negative_weights(client):
    token = await _register_and_login(client, "recruiter34@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=1)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank",
        json={"weights": {"skills": 1.2, "experience": -0.2, "education": 0.0}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_rank_job_with_no_scored_candidates(client):
    token = await _register_and_login(client, "recruiter35@company.com")
    job_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Empty Job", "description": "No applicants yet."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total_candidates"] == 0
    assert body["ranking"] == []


async def test_rank_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "recruiter36@company.com")
    resp = await client.post(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/rank",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_trigger_ranking(client):
    admin_token = await _register_and_login(client, "admin20@company.com")
    job_id, _ = await _prepare_scored_job(client, admin_token, candidate_count=1)
    viewer_token = await _register_and_login(client, "viewer10@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_get_ranking_returns_persisted_order(client):
    token = await _register_and_login(client, "recruiter37@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=2)
    await client.post(f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {token}"})

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/ranking", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert all(c["rank"] is not None for c in body)


async def test_get_ranking_before_ranking_returns_empty(client):
    token = await _register_and_login(client, "recruiter38@company.com")
    job_id, _ = await _prepare_scored_job(client, token, candidate_count=1)

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/ranking", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json() == []  # scored but not yet ranked


async def test_viewer_can_read_ranking(client):
    admin_token = await _register_and_login(client, "admin21@company.com")
    job_id, _ = await _prepare_scored_job(client, admin_token, candidate_count=1)
    await client.post(f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {admin_token}"})
    viewer_token = await _register_and_login(client, "viewer11@company.com", role="viewer")

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/ranking", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 200  # read-only access is the viewer role's purpose


REPORT_SUMMARY_JSON = '{"summary": "Candidates screened for this backend role."}'
FEEDBACK_JSON = """{
  "summary": "Solid candidate.",
  "strengths": ["Python"],
  "weaknesses": [],
  "risk_factors": [],
  "improvement_suggestions": ["Explore infrastructure tooling"]
}"""


async def _prepare_job_with_full_pipeline(client, token, candidate_count=2):
    """Run the complete pipeline so a report has real data to aggregate."""
    job_id, resume_ids = await _prepare_scored_job(client, token, candidate_count=candidate_count)
    await client.post(f"/api/v1/jobs/{job_id}/rank", headers={"Authorization": f"Bearer {token}"})

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [FEEDBACK_JSON]
    )
    try:
        for resume_id in resume_ids:
            await client.post(
                f"/api/v1/resumes/{resume_id}/feedback", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )
    return job_id, resume_ids


async def test_generate_report_success(client):
    token = await _register_and_login(client, "recruiter60@company.com")
    job_id, _ = await _prepare_job_with_full_pipeline(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [REPORT_SUMMARY_JSON]
    )
    try:
        resp = await client.post(
            f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total_candidates"] == 2
    assert body["report"]["id"]
    # file_path is an internal storage detail and must not leak.
    assert "file_path" not in body["report"]


async def test_download_report_returns_a_real_pdf(client):
    token = await _register_and_login(client, "recruiter61@company.com")
    job_id, _ = await _prepare_job_with_full_pipeline(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [REPORT_SUMMARY_JSON]
    )
    try:
        gen_resp = await client.post(
            f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )
    report_id = gen_resp.json()["report"]["id"]

    dl_resp = await client.get(
        f"/api/v1/reports/{report_id}/download", headers={"Authorization": f"Bearer {token}"}
    )
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert dl_resp.content[:4] == b"%PDF"
    assert len(dl_resp.content) > 1000


async def test_report_for_job_without_scores_is_a_handled_failure(client):
    token = await _register_and_login(client, "recruiter62@company.com")
    job_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Empty Role", "description": "No applicants."},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = job_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "no scored candidates" in body["reasoning"].lower()


async def test_report_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "recruiter63@company.com")
    resp = await client.post(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/report",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_generate_report(client):
    admin_token = await _register_and_login(client, "admin50@company.com")
    job_id, _ = await _prepare_job_with_full_pipeline(client, admin_token, candidate_count=1)
    viewer_token = await _register_and_login(client, "viewer40@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_unrelated_viewer_cannot_download_a_report(client):
    """UPDATED IN PHASE 19.

    This test previously asserted that ANY viewer could download ANY
    report, on the reasoning that "read-only access is the viewer role's
    purpose". That was wrong, and it encoded the Phase 13 IDOR as expected
    behavior: reports contain every candidate's name, score, and hiring
    recommendation, and a viewer with no relationship to the job has no
    business reading them.

    "Viewer" means cannot modify — not can read everything.
    """
    admin_token = await _register_and_login(client, "admin51@company.com")
    job_id, _ = await _prepare_job_with_full_pipeline(client, admin_token, candidate_count=1)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [REPORT_SUMMARY_JSON]
    )
    try:
        gen_resp = await client.post(
            f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {admin_token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )
    report_id = gen_resp.json()["report"]["id"]

    viewer_token = await _register_and_login(client, "viewer41@company.com", role="viewer")
    resp = await client.get(
        f"/api/v1/reports/{report_id}/download", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    # 404 rather than 403: a 403 would confirm the report ID is valid.
    assert resp.status_code == 404


async def test_list_reports_for_job(client):
    token = await _register_and_login(client, "recruiter64@company.com")
    job_id, _ = await _prepare_job_with_full_pipeline(client, token, candidate_count=1)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [REPORT_SUMMARY_JSON]
    )
    try:
        await client.post(f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"})
        await client.post(f"/api/v1/jobs/{job_id}/report", headers={"Authorization": f"Bearer {token}"})
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/reports", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    # Reports are point-in-time snapshots, so both are retained.
    assert len(resp.json()) == 2


async def test_download_nonexistent_report_returns_404(client):
    token = await _register_and_login(client, "recruiter65@company.com")
    resp = await client.get(
        "/api/v1/reports/00000000-0000-0000-0000-000000000000/download",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404
