"""API-level tests for resume upload/list/get/download/parse."""
import io

from app.api.deps import get_llm_provider_dependency
from app.main import app
from tests.fakes import VALID_PARSED_RESUME_JSON, ScriptedLLMProvider


def _build_real_pdf_bytes(text: str) -> bytes:
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
    login_resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login_resp.json()["access_token"]


async def _create_open_job(client, token: str) -> str:
    resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Backend Engineer", "description": "Build APIs."},
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()["id"]


async def test_upload_resume_succeeds_for_recruiter(client):
    token = await _register_and_login(client, "recruiter1@company.com")  # bootstrap admin
    job_id = await _create_open_job(client, token)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF fake resume content", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "uploaded"
    assert body["candidate_id"] is None
    assert "storage_path" not in body  # never leak the internal path


async def test_viewer_cannot_upload_resume(client):
    admin_token = await _register_and_login(client, "admin5@company.com")
    job_id = await _create_open_job(client, admin_token)
    viewer_token = await _register_and_login(client, "viewer2@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


async def test_upload_invalid_file_type_rejected(client):
    token = await _register_and_login(client, "recruiter2@company.com")
    job_id = await _create_open_job(client, token)

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("malware.exe", b"MZ fake exe", "application/octet-stream")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


async def test_upload_content_mismatch_rejected(client):
    token = await _register_and_login(client, "recruiter3@company.com")
    job_id = await _create_open_job(client, token)

    # .pdf extension but content that isn't actually a PDF.
    resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"this is definitely not a pdf", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


async def test_upload_to_nonexistent_job_returns_404(client):
    token = await _register_and_login(client, "recruiter4@company.com")
    resp = await client.post(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_upload_to_closed_job_returns_409(client):
    token = await _register_and_login(client, "recruiter5@company.com")
    create_resp = await client.post(
        "/api/v1/jobs",
        json={"title": "Old Role", "description": "...", "status": "closed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    job_id = create_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


async def test_list_resumes_for_job(client):
    token = await _register_and_login(client, "recruiter6@company.com")
    job_id = await _create_open_job(client, token)
    await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.get(
        f"/api/v1/jobs/{job_id}/resumes", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_get_resume_by_id(client):
    token = await _register_and_login(client, "recruiter7@company.com")
    job_id = await _create_open_job(client, token)
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/resumes/{resume_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == resume_id


async def test_get_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "recruiter8@company.com")
    resp = await client.get(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_download_resume_returns_original_bytes(client):
    token = await _register_and_login(client, "recruiter9@company.com")
    job_id = await _create_open_job(client, token)
    original_content = b"%PDF-1.4 this is the original resume content"
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("my_resume.pdf", original_content, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    resp = await client.get(
        f"/api/v1/resumes/{resume_id}/download", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.content == original_content
    assert resp.headers["content-type"] == "application/pdf"
    assert "my_resume.pdf" in resp.headers["content-disposition"]


async def test_viewer_can_view_but_not_upload(client):
    admin_token = await _register_and_login(client, "admin6@company.com")
    job_id = await _create_open_job(client, admin_token)
    await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", b"%PDF x", "application/pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    viewer_token = await _register_and_login(client, "viewer3@company.com", role="viewer")

    # Viewer CAN list/view (read-only access is the whole point of the role)
    list_resp = await client.get(
        f"/api/v1/jobs/{job_id}/resumes", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_parse_resume_success(client):
    token = await _register_and_login(client, "recruiter10@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Jane Doe resume content for parsing")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    parse_resp = await client.post(
        f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
    )
    assert parse_resp.status_code == 200
    body = parse_resp.json()
    assert body["success"] is True
    assert body["resume"]["status"] == "parsed"
    assert body["resume"]["candidate_id"] is not None
    assert body["resume"]["parsed_data"]["full_name"] == "Jane Doe"


async def test_parse_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "recruiter11@company.com")
    resp = await client.post(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000/parse",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_trigger_parse(client):
    admin_token = await _register_and_login(client, "admin7@company.com")
    job_id = await _create_open_job(client, admin_token)
    real_pdf = _build_real_pdf_bytes("Some resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resume_id = upload_resp.json()["id"]
    viewer_token = await _register_and_login(client, "viewer4@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_parse_reports_failure_without_raising_http_error(client):
    token = await _register_and_login(client, "recruiter12@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Some resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    # Force the LLM to return unparseable garbage on both attempts.
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        ["garbage", "still garbage"]
    )
    try:
        parse_resp = await client.post(
            f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        # Restore the default for any subsequent test using this client.
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    assert parse_resp.status_code == 200  # a handled failure, not an HTTP error
    body = parse_resp.json()
    assert body["success"] is False
    assert body["resume"]["status"] == "failed"


async def test_extract_skills_after_parse_success(client):
    token = await _register_and_login(client, "recruiter13@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Jane Doe resume for skill extraction")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})

    extract_resp = await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    assert extract_resp.status_code == 200
    body = extract_resp.json()
    assert body["success"] is True
    resolved_names = {s["canonical_name"] for s in body["resolved_skills"]}
    assert resolved_names == {"Python", "SQL"}  # from VALID_PARSED_RESUME_JSON's skills list


async def test_extract_skills_before_parse_is_a_handled_failure(client):
    token = await _register_and_login(client, "recruiter14@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Some resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    extract_resp = await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    assert extract_resp.status_code == 200  # handled failure, not an HTTP error
    body = extract_resp.json()
    assert body["success"] is False
    assert "must be parsed" in body["reasoning"].lower()


async def test_extract_skills_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "recruiter15@company.com")
    resp = await client.post(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000/extract-skills",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_extract_skills(client):
    admin_token = await _register_and_login(client, "admin8@company.com")
    job_id = await _create_open_job(client, admin_token)
    real_pdf = _build_real_pdf_bytes("Some resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resume_id = upload_resp.json()["id"]
    viewer_token = await _register_and_login(client, "viewer5@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_list_resume_skills_endpoint(client):
    token = await _register_and_login(client, "recruiter16@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Jane Doe resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})
    await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )

    list_resp = await client.get(
        f"/api/v1/resumes/{resume_id}/skills", headers={"Authorization": f"Bearer {token}"}
    )
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert len(body) == 2
    names = {s["name"] for s in body}
    assert names == {"Python", "SQL"}
    assert all(s["confidence"] == 1.0 for s in body)


MATCH_ANALYSIS_JSON = """{
  "strengths": ["Strong Python background"],
  "weaknesses": ["No cloud experience listed"]
}"""


async def _prepare_matched_resume(client, token, job_payload=None):
    """Upload -> parse -> extract skills, leaving the resume ready to match."""
    job_payload = job_payload or {
        "title": "Backend Engineer",
        "description": "Build APIs.",
        "required_skills": ["Python", "SQL"],
    }
    job_resp = await client.post(
        "/api/v1/jobs", json=job_payload, headers={"Authorization": f"Bearer {token}"}
    )
    job_id = job_resp.json()["id"]
    real_pdf = _build_real_pdf_bytes("Jane Doe resume content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})
    await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    return job_id, resume_id


async def test_match_resume_produces_explainable_score(client):
    token = await _register_and_login(client, "recruiter17@company.com")
    _, resume_id = await _prepare_matched_resume(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [MATCH_ANALYSIS_JSON]
    )
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["score"]["similarity_score"] == 1.0  # Python + SQL both matched
    assert set(body["score"]["skill_overlap"]) == {"Python", "SQL"}
    # The breakdown must expose every component, not just a number.
    assert len(body["breakdown"]["components"]) == 3
    assert body["explanation"]


async def test_match_is_deterministic_across_repeated_calls(client):
    token = await _register_and_login(client, "recruiter18@company.com")
    _, resume_id = await _prepare_matched_resume(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [MATCH_ANALYSIS_JSON]
    )
    try:
        scores = []
        for _ in range(3):
            resp = await client.post(
                f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
            )
            scores.append(resp.json()["score"]["similarity_score"])
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    assert len(set(scores)) == 1  # identical every time


async def test_match_reports_missing_required_skills(client):
    token = await _register_and_login(client, "recruiter19@company.com")
    _, resume_id = await _prepare_matched_resume(
        client,
        token,
        job_payload={
            "title": "DevOps Engineer",
            "description": "Infra work.",
            "required_skills": ["Python", "Kubernetes", "Terraform"],
        },
    )

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [MATCH_ANALYSIS_JSON]
    )
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    body = resp.json()
    assert set(body["score"]["missing_skills"]) == {"Kubernetes", "Terraform"}
    assert body["score"]["similarity_score"] < 1.0


async def test_match_unparsed_resume_is_a_handled_failure(client):
    token = await _register_and_login(client, "recruiter20@company.com")
    job_id = await _create_open_job(client, token)
    real_pdf = _build_real_pdf_bytes("Some content")
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", real_pdf, "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200  # handled failure, not an HTTP error
    assert resp.json()["success"] is False


async def test_match_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "recruiter21@company.com")
    resp = await client.post(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000/match",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_trigger_match(client):
    admin_token = await _register_and_login(client, "admin14@company.com")
    _, resume_id = await _prepare_matched_resume(client, admin_token)
    viewer_token = await _register_and_login(client, "viewer7@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 403


async def test_get_score_before_matching_returns_404(client):
    token = await _register_and_login(client, "recruiter22@company.com")
    _, resume_id = await _prepare_matched_resume(client, token)

    resp = await client.get(
        f"/api/v1/resumes/{resume_id}/score", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 404


async def test_get_score_after_matching_succeeds(client):
    token = await _register_and_login(client, "recruiter23@company.com")
    _, resume_id = await _prepare_matched_resume(client, token)

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

    resp = await client.get(
        f"/api/v1/resumes/{resume_id}/score", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["resume_id"] == resume_id


async def test_viewer_can_read_score(client):
    admin_token = await _register_and_login(client, "admin15@company.com")
    _, resume_id = await _prepare_matched_resume(client, admin_token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [MATCH_ANALYSIS_JSON]
    )
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/match", headers={"Authorization": f"Bearer {admin_token}"}
        )
    finally:
        app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
            [VALID_PARSED_RESUME_JSON]
        )

    viewer_token = await _register_and_login(client, "viewer8@company.com", role="viewer")
    resp = await client.get(
        f"/api/v1/resumes/{resume_id}/score", headers={"Authorization": f"Bearer {viewer_token}"}
    )
    assert resp.status_code == 200  # read-only access is the viewer role's purpose


QUESTIONS_JSON = """{
  "questions": [
    {"question": "How would you containerize the service you built?",
     "category": "technical", "difficulty": "medium",
     "rationale": "Probes a gap found during matching."},
    {"question": "Describe a technical disagreement you navigated.",
     "category": "behavioral", "difficulty": "easy",
     "rationale": "Collaboration signal."}
  ]
}"""


def _use_questions_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [QUESTIONS_JSON]
    )


def _restore_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [VALID_PARSED_RESUME_JSON]
    )


async def _prepare_parsed_resume(client, token, email_suffix=""):
    job_id = await _create_open_job(client, token)
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", _build_real_pdf_bytes("Jane Doe resume"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})
    await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    return job_id, resume_id


async def test_generate_interview_questions_success(client):
    token = await _register_and_login(client, "recruiter40@company.com")
    _, resume_id = await _prepare_parsed_resume(client, token)

    _use_questions_llm()
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/interview-questions",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["questions"]) == 2
    assert body["by_category"] == {"technical": 1, "behavioral": 1}
    assert all(q["rationale"] for q in body["questions"])


async def test_generate_interview_questions_failure_saves_nothing(client):
    token = await _register_and_login(client, "recruiter41@company.com")
    _, resume_id = await _prepare_parsed_resume(client, token)

    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        ["garbage", "still garbage"]
    )
    try:
        resp = await client.post(
            f"/api/v1/resumes/{resume_id}/interview-questions",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200  # handled failure, not an HTTP error
    body = resp.json()
    assert body["success"] is False
    assert body["questions"] == []

    # Confirm nothing was persisted either.
    list_resp = await client.get(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.json() == []


async def test_regenerating_replaces_previous_questions(client):
    token = await _register_and_login(client, "recruiter42@company.com")
    _, resume_id = await _prepare_parsed_resume(client, token)

    _use_questions_llm()
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/interview-questions",
            headers={"Authorization": f"Bearer {token}"},
        )
        await client.post(
            f"/api/v1/resumes/{resume_id}/interview-questions",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    list_resp = await client.get(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert len(list_resp.json()) == 2  # not 4


async def test_generate_questions_unparsed_resume_is_handled_failure(client):
    token = await _register_and_login(client, "recruiter43@company.com")
    job_id = await _create_open_job(client, token)
    upload_resp = await client.post(
        f"/api/v1/jobs/{job_id}/resumes",
        files={"file": ("resume.pdf", _build_real_pdf_bytes("content"), "application/pdf")},
        headers={"Authorization": f"Bearer {token}"},
    )
    resume_id = upload_resp.json()["id"]

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is False


async def test_generate_questions_nonexistent_resume_returns_404(client):
    token = await _register_and_login(client, "recruiter44@company.com")
    resp = await client.post(
        "/api/v1/resumes/00000000-0000-0000-0000-000000000000/interview-questions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


async def test_viewer_cannot_generate_questions(client):
    admin_token = await _register_and_login(client, "admin30@company.com")
    _, resume_id = await _prepare_parsed_resume(client, admin_token)
    viewer_token = await _register_and_login(client, "viewer20@company.com", role="viewer")

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 403


async def test_viewer_can_read_questions(client):
    admin_token = await _register_and_login(client, "admin31@company.com")
    _, resume_id = await _prepare_parsed_resume(client, admin_token)
    _use_questions_llm()
    try:
        await client.post(
            f"/api/v1/resumes/{resume_id}/interview-questions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
    finally:
        _restore_llm()

    viewer_token = await _register_and_login(client, "viewer21@company.com", role="viewer")
    resp = await client.get(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_question_count_out_of_range_rejected_by_schema(client):
    token = await _register_and_login(client, "recruiter45@company.com")
    _, resume_id = await _prepare_parsed_resume(client, token)

    resp = await client.post(
        f"/api/v1/resumes/{resume_id}/interview-questions",
        json={"question_count": 500},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
