import uuid
import pytest


def register_and_login(client, email_prefix="learner"):
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "InitialPassword123!"

    reg_resp = client.post("/auth/register", json={"email": email, "password": password})
    assert reg_resp.status_code == 201

    login_resp = client.post("/auth/login", json={"email": email, "password": password})
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return email, password, headers


def test_get_profile_auto_provisioning(client):
    email, password, headers = register_and_login(client, "autouser")

    # Call GET /profile/me
    res = client.get("/profile/me", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["email"] == email
    assert data["user_id"] is not None
    assert data["id"] is not None
    assert "autouser" in data["display_name"].lower()


def test_update_profile_identity(client):
    email, password, headers = register_and_login(client, "alex")

    # Update display name and bio
    update_payload = {
        "display_name": "Alex Vance",
        "bio": "Staff Systems Engineer & Rust Enthusiast",
    }
    patch_res = client.patch("/profile/me", json=update_payload, headers=headers)
    assert patch_res.status_code == 200
    updated = patch_res.json()

    assert updated["display_name"] == "Alex Vance"
    assert updated["bio"] == "Staff Systems Engineer & Rust Enthusiast"

    # Verify persistent on subsequent GET
    get_res = client.get("/profile/me", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["display_name"] == "Alex Vance"
    assert get_res.json()["bio"] == "Staff Systems Engineer & Rust Enthusiast"


def test_learner_settings_lifecycle(client):
    email, password, headers = register_and_login(client, "settingsuser")

    # 1. Check default settings
    get_res = client.get("/profile/me/learning", headers=headers)
    assert get_res.status_code == 200
    defaults = get_res.json()
    assert defaults["experience_level"] == "intermediate"
    assert defaults["preferred_language"] == "python"
    assert defaults["explanation_depth"] == "internals"
    assert "stats" in defaults
    assert defaults["stats"]["total_journeys"] == 0

    # 2. Update settings
    patch_payload = {
        "experience_level": "staff",
        "preferred_language": "rust",
        "explanation_depth": "mechanics",
        "learning_style": "code_first",
        "target_goals": "Deep dive into Linux eBPF and kernel internals",
    }
    patch_res = client.patch("/profile/me/learning", json=patch_payload, headers=headers)
    assert patch_res.status_code == 200
    updated = patch_res.json()

    assert updated["experience_level"] == "staff"
    assert updated["preferred_language"] == "rust"
    assert updated["explanation_depth"] == "mechanics"
    assert updated["learning_style"] == "code_first"
    assert updated["target_goals"] == "Deep dive into Linux eBPF and kernel internals"


def test_change_password_success(client):
    email, old_password, headers = register_and_login(client, "pwuser")
    new_password = "BrandNewSuperSecret2026!"

    # Change password
    change_res = client.post(
        "/profile/me/change-password",
        json={"current_password": old_password, "new_password": new_password},
        headers=headers,
    )
    assert change_res.status_code == 200
    assert "message" in change_res.json()

    # Old password must now fail
    fail_login = client.post("/auth/login", json={"email": email, "password": old_password})
    assert fail_login.status_code == 401

    # New password must succeed
    succ_login = client.post("/auth/login", json={"email": email, "password": new_password})
    assert succ_login.status_code == 200
    assert "access_token" in succ_login.json()


def test_change_password_invalid_current(client):
    email, password, headers = register_and_login(client, "wrongpw")

    # Provide incorrect current password
    change_res = client.post(
        "/profile/me/change-password",
        json={"current_password": "WrongPassword123!", "new_password": "ValidNewPassword888!"},
        headers=headers,
    )
    assert change_res.status_code == 400
    assert "incorrect" in change_res.json()["detail"].lower()


def test_unauthenticated_profile_endpoints(client):
    # GET /profile/me
    res1 = client.get("/profile/me")
    assert res1.status_code == 401

    # PATCH /profile/me
    res2 = client.patch("/profile/me", json={"display_name": "Ghost"})
    assert res2.status_code == 401

    # GET /profile/me/learning
    res3 = client.get("/profile/me/learning")
    assert res3.status_code == 401

    # POST /profile/me/change-password
    res4 = client.post("/profile/me/change-password", json={"current_password": "a", "new_password": "b"})
    assert res4.status_code == 401
