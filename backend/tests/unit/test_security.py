import pytest

from app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_jwt_create_and_decode_roundtrip():
    token = create_access_token(subject="user-123", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "admin"


def test_jwt_rejects_tampered_token():
    token = create_access_token(subject="user-123", role="admin")
    # Tamper with the PAYLOAD segment, not the signature's last character.
    # A JWT's signature is base64url-encoded, and altering only its final
    # character can decode to the same underlying bytes (base64 padding),
    # leaving the token genuinely valid — that made an earlier version of
    # this test intermittently fail. Corrupting the payload is unambiguous.
    header, payload, signature = token.split(".")
    tampered_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    tampered = f"{header}.{tampered_payload}.{signature}"
    with pytest.raises(TokenError):
        decode_access_token(tampered)


def test_jwt_rejects_expired_token():
    token = create_access_token(subject="user-123", role="admin", expires_minutes=-1)
    with pytest.raises(TokenError):
        decode_access_token(token)
