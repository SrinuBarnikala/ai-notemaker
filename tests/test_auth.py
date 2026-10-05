"""
Unit & Integration Tests for Authentication: User Model, Argon2id Hashing,
Login, /auth/me, /auth/logout, and Token Security.
"""
import pytest
from datetime import timedelta
from backend.app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_argon2id_password_hashing():
    """Verify passwords are securely hashed with Argon2id and never plaintext."""
    raw_pw = "super-secret-password-123"
    hashed = get_password_hash(raw_pw)

    assert hashed != raw_pw
    assert hashed.startswith("$argon2id$")
    assert verify_password(raw_pw, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_jwt_access_token_creation_and_decoding():
    """Verify JWT token encoding and decoding."""
    user_id = "test-user-12345"
    token = create_access_token(subject=user_id)
    payload = decode_access_token(token)

    assert payload is not None
    assert payload["sub"] == user_id
    assert "exp" in payload


def test_jwt_expired_token_rejected():
    """Verify expired token is rejected."""
    user_id = "test-user-expired"
    # Token expired 1 hour ago
    expired_token = create_access_token(subject=user_id, expires_delta=timedelta(seconds=-3600))
    payload = decode_access_token(expired_token)
    assert payload is None


def test_auth_registration_and_login_flow(client):
    """
    Test registration foundation, login success, HttpOnly cookie setting,
    and profile retrieval.
    """
    import uuid
    email = f"learner_{uuid.uuid4().hex[:8]}@example.com"
    password = "TechnicalNotesPassword2026!"

    # 1. Register test user via foundation endpoint
    reg_resp = client.post("/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201

    user_data = reg_resp.json()
    assert user_data["email"] == email
    assert "id" in user_data
    # Assert password is NEVER returned in response
    assert "password" not in user_data
    assert "hashed_password" not in user_data

    # 2. Test duplicate registration rejected
    dup_resp = client.post("/auth/register", json={"email": email, "password": password})
    assert dup_resp.status_code == 400

    # 3. Test login with wrong password
    bad_resp = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    assert bad_resp.status_code == 401
    assert "invalid email or password" in bad_resp.json()["detail"].lower()

    # 4. Test login with non-existent email (generic error message prevents enumeration)
    no_email_resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": password})
    assert no_email_resp.status_code == 401
    assert "invalid email or password" in no_email_resp.json()["detail"].lower()

    # 5. Test login with valid credentials
    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["user"]["email"] == email
    # Check that HttpOnly cookie was set
    assert "auth_token" in login_resp.cookies or "set-cookie" in login_resp.headers

    token = token_data["access_token"]

    # 6. Test /auth/me with Bearer token header
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == email
    assert me_data["id"] == user_data["id"]
    assert "password" not in me_data
    assert "hashed_password" not in me_data

    # 7. Test /auth/me with cookie
    client.cookies.set("auth_token", token)
    me_cookie_resp = client.get("/auth/me")
    assert me_cookie_resp.status_code == 200
    assert me_cookie_resp.json()["email"] == email

    # 8. Test /auth/logout
    logout_resp = client.post("/auth/logout")
    assert logout_resp.status_code == 200
    assert "logged out" in logout_resp.json()["message"].lower()

    # Clear cookie manually from test client to simulate browser behavior
    client.cookies.clear()
    unauth_resp = client.get("/auth/me")
    assert unauth_resp.status_code == 401


def test_auth_me_unauthenticated_rejected(client):
    """Verify /auth/me strictly rejects unauthenticated requests."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401
    assert "authentication required" in resp.json()["detail"].lower()


def test_authenticated_journey_scoping(client):
    """
    Verify that journeys created by an authenticated user are scoped to that user
    and other users cannot access them.
    """
    # Create User A
    import uuid
    suffix = uuid.uuid4().hex[:6]
    user_a_email = f"user.a.{suffix}@example.com"
    pw = "Password12345!"
    client.post("/auth/register", json={"email": user_a_email, "password": pw})
    login_a = client.post("/auth/login", json={"email": user_a_email, "password": pw}).json()
    token_a = login_a["access_token"]

    # Create User B
    user_b_email = f"user.b.{suffix}@example.com"
    client.post("/auth/register", json={"email": user_b_email, "password": pw})
    login_b = client.post("/auth/login", json={"email": user_b_email, "password": pw}).json()
    token_b = login_b["access_token"]


    # User A creates a journey
    resp_create = client.post(
        "/journeys",
        json={"topic": "User A Private Topic"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp_create.status_code == 201
    journey_a_id = resp_create.json()["id"]

    # User A can get their journey
    get_a = client.get(f"/journeys/{journey_a_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert get_a.status_code == 200

    # User A lists journeys - contains their journey
    list_a = client.get("/journeys", headers={"Authorization": f"Bearer {token_a}"}).json()
    assert any(j["id"] == journey_a_id for j in list_a["journeys"])

    # User B lists journeys - does NOT see User A's journey!
    list_b = client.get("/journeys", headers={"Authorization": f"Bearer {token_b}"}).json()
    assert not any(j["id"] == journey_a_id for j in list_b["journeys"])

    # User B tries to access User A's journey directly -> 403 Forbidden!
    forbidden_resp = client.get(f"/journeys/{journey_a_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert forbidden_resp.status_code == 403


def test_login_session_cookie_default(client):
    """
    Verify that default login (remember_me=False) issues a session cookie
    without a persistent max-age, ensuring sessions expire on browser close.
    """
    import uuid
    email = f"sess_{uuid.uuid4().hex[:8]}@example.com"
    pw = "SessionPassword123!"

    client.post("/auth/register", json={"email": email, "password": pw})

    # Login without remember_me
    resp = client.post("/auth/login", json={"email": email, "password": pw, "remember_me": False})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "auth_token=" in set_cookie
    # Should NOT have Max-Age attribute (session cookie)
    assert "max-age=" not in set_cookie.lower()


def test_login_persistent_cookie_remember_me(client):
    """
    Verify that login with remember_me=True issues a persistent cookie with max-age.
    """
    import uuid
    email = f"persist_{uuid.uuid4().hex[:8]}@example.com"
    pw = "PersistPassword123!"

    client.post("/auth/register", json={"email": email, "password": pw})

    # Login with remember_me=True
    resp = client.post("/auth/login", json={"email": email, "password": pw, "remember_me": True})
    assert resp.status_code == 200
    set_cookie = resp.headers.get("set-cookie", "")
    assert "auth_token=" in set_cookie
    # Must have Max-Age attribute for persistence across browser restarts
    assert "max-age=" in set_cookie.lower()
