"""
API-level tests for /api/v1/auth/*, exercising the real FastAPI routes over
HTTP (via httpx's ASGI transport) against an in-memory SQLite database.
"""


async def test_first_registered_user_becomes_admin(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "founder@company.com", "password": "supersecret1", "full_name": "Founder"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "admin"


async def test_second_user_defaults_to_recruiter_and_cannot_self_promote(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "founder@company.com", "password": "supersecret1", "full_name": "Founder"},
    )

    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "recruiter@company.com", "password": "supersecret1", "full_name": "Recruiter"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "recruiter"

    escalation_attempt = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "hacker@company.com",
            "password": "supersecret1",
            "full_name": "Hacker",
            "role": "admin",
        },
    )
    assert escalation_attempt.status_code == 403


async def test_duplicate_email_rejected(client):
    payload = {"email": "dup@company.com", "password": "supersecret1", "full_name": "Dup"}
    first = await client.post("/api/v1/auth/register", json=payload)
    second = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


async def test_password_too_short_rejected_by_validation(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "short@company.com", "password": "abc", "full_name": "Short"},
    )
    assert resp.status_code == 422


async def test_login_and_access_protected_me_route(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user@company.com", "password": "supersecret1", "full_name": "User"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "user@company.com", "password": "supersecret1"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "user@company.com"


async def test_login_with_wrong_password_rejected(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "user2@company.com", "password": "supersecret1", "full_name": "User2"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "user2@company.com", "password": "wrongpassword"},
    )
    assert login_resp.status_code == 401


async def test_me_route_rejects_missing_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_admin_only_route_forbidden_for_recruiter_but_allowed_for_admin(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "admin1@company.com", "password": "supersecret1", "full_name": "Admin"},
    )
    await client.post(
        "/api/v1/auth/register",
        json={"email": "rec1@company.com", "password": "supersecret1", "full_name": "Rec"},
    )

    recruiter_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "rec1@company.com", "password": "supersecret1"},
    )
    recruiter_token = recruiter_login.json()["access_token"]
    forbidden_resp = await client.get(
        "/api/v1/auth/admin-only", headers={"Authorization": f"Bearer {recruiter_token}"}
    )
    assert forbidden_resp.status_code == 403

    admin_login = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin1@company.com", "password": "supersecret1"},
    )
    admin_token = admin_login.json()["access_token"]
    allowed_resp = await client.get(
        "/api/v1/auth/admin-only", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert allowed_resp.status_code == 200
