"""API-level tests for RAG question answering."""
import io

from app.api.deps import get_llm_provider_dependency
from app.main import app
from tests.fakes import VALID_PARSED_RESUME_JSON, ScriptedLLMProvider

GROUNDED = """{
  "answer": "Jane Doe lists Python and SQL [1].",
  "claims": [{"text": "Jane Doe lists Python and SQL.", "source_ids": [1]}],
  "insufficient_evidence": false
}"""

FABRICATED = """{
  "answer": "Five candidates have 15 years of Rust experience [42].",
  "claims": [{"text": "Five candidates have 15 years of Rust experience.", "source_ids": [42]}],
  "insufficient_evidence": false
}"""


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


async def _index_a_resume(client, token):
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
    resume_id = upload.json()["id"]
    await client.post(f"/api/v1/resumes/{resume_id}/parse", headers={"Authorization": f"Bearer {token}"})
    await client.post(
        f"/api/v1/resumes/{resume_id}/extract-skills", headers={"Authorization": f"Bearer {token}"}
    )
    await client.post(f"/api/v1/resumes/{resume_id}/index", headers={"Authorization": f"Bearer {token}"})
    return job_id, resume_id


def _use_llm(response: str):
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider([response])


def _restore_llm():
    app.dependency_overrides[get_llm_provider_dependency] = lambda: ScriptedLLMProvider(
        [VALID_PARSED_RESUME_JSON]
    )


async def test_ask_returns_grounded_answer_with_sources(client):
    token = await _register_and_login(client, "rag1@company.com")
    await _index_a_resume(client, token)

    _use_llm(GROUNDED)
    try:
        resp = await client.post(
            "/api/v1/rag/ask",
            json={"question": "Which candidates know Python?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer_rejected"] is False
    assert len(body["claims"]) == 1
    assert body["claims"][0]["source_ids"] == [1]
    # Full source text returned so claims can be checked independently.
    assert body["sources"][0]["text"]


async def test_ask_rejects_an_answer_with_fabricated_citations(client):
    token = await _register_and_login(client, "rag2@company.com")
    await _index_a_resume(client, token)

    _use_llm(FABRICATED)
    try:
        resp = await client.post(
            "/api/v1/rag/ask",
            json={"question": "Who has 15 years of Rust?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _restore_llm()

    body = resp.json()
    assert body["answer_rejected"] is True
    assert body["claims"] == []
    assert body["citation_warnings"]
    # Sources still returned for manual review.
    assert body["sources"]


async def test_ask_with_no_indexed_resumes(client):
    token = await _register_and_login(client, "rag3@company.com")
    resp = await client.post(
        "/api/v1/rag/ask",
        json={"question": "Who knows Python?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["insufficient_evidence"] is True


async def test_empty_question_rejected_by_schema(client):
    token = await _register_and_login(client, "rag4@company.com")
    resp = await client.post(
        "/api/v1/rag/ask", json={"question": ""}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 422


async def test_out_of_range_top_k_rejected_by_schema(client):
    token = await _register_and_login(client, "rag5@company.com")
    resp = await client.post(
        "/api/v1/rag/ask",
        json={"question": "Who knows Python?", "top_k": 999},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


async def test_invalid_job_id_returns_400(client):
    token = await _register_and_login(client, "rag6@company.com")
    resp = await client.post(
        "/api/v1/rag/ask",
        json={"question": "Who knows Python?", "job_id": "not-a-uuid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


async def test_viewer_can_ask(client):
    # Read-only question answering is exactly what the viewer role is for.
    admin_token = await _register_and_login(client, "rag7@company.com")
    await _index_a_resume(client, admin_token)
    viewer_token = await _register_and_login(client, "ragviewer@company.com", role="viewer")

    _use_llm(GROUNDED)
    try:
        resp = await client.post(
            "/api/v1/rag/ask",
            json={"question": "Who knows Python?"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
    finally:
        _restore_llm()

    assert resp.status_code == 200


async def test_unauthenticated_ask_is_rejected(client):
    resp = await client.post("/api/v1/rag/ask", json={"question": "Who knows Python?"})
    assert resp.status_code == 401
