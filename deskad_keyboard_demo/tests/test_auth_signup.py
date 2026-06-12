"""회원가입(/auth/signup, 가입 코드, PBKDF2 저장, 영속성) 테스트."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend import auth
from backend.main import app
from backend.schemas import SignupRequest

SIGNUP_CODE = "invite-2026"
PASSWORD = "new-user-password"


@pytest.fixture(autouse=True)
def _clean_auth_state(monkeypatch, tmp_path):
    auth.reset_state()
    monkeypatch.delenv("DESKAD_LOGIN_ID", raising=False)
    monkeypatch.delenv("DESKAD_LOGIN_PASSWORD_SHA256", raising=False)
    monkeypatch.setenv("DESKAD_SIGNUP_CODE", SIGNUP_CODE)
    monkeypatch.setenv("DESKAD_USERS_PATH", str(tmp_path / "users.json"))
    yield
    auth.reset_state()


@pytest.fixture()
def client():
    return TestClient(app)


# --- 스키마 ---

def test_signup_request_rejects_bad_username_and_short_password():
    with pytest.raises(ValidationError):
        SignupRequest(username="ab", password=PASSWORD, signup_code=SIGNUP_CODE)
    with pytest.raises(ValidationError):
        SignupRequest(username="한글아이디", password=PASSWORD, signup_code=SIGNUP_CODE)
    with pytest.raises(ValidationError):
        SignupRequest(username="newuser", password="short", signup_code=SIGNUP_CODE)
    with pytest.raises(ValidationError):
        SignupRequest(username="newuser", password=PASSWORD, signup_code="")


# --- /auth/signup ---

def test_signup_success_auto_logs_in(client):
    response = client.post(
        "/auth/signup",
        json={"username": "newuser", "password": PASSWORD, "signup_code": SIGNUP_CODE},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["token"]
    assert body["display_name"] == "newuser"
    assert auth.is_token_valid(body["token"])


def test_signup_stores_salted_pbkdf2_not_plaintext(tmp_path):
    result = auth.signup("newuser", PASSWORD, SIGNUP_CODE)
    assert result["ok"] is True

    raw = (tmp_path / "users.json").read_text(encoding="utf-8")
    assert PASSWORD not in raw
    record = json.loads(raw)["newuser"]
    assert record["salt"]
    assert record["password_pbkdf2"]
    assert record["iterations"] == auth.PBKDF2_ITERATIONS


def test_signup_then_login_roundtrip():
    auth.signup("newuser", PASSWORD, SIGNUP_CODE)

    assert auth.login("newuser", PASSWORD)["ok"] is True
    wrong = auth.login("newuser", "wrong-password")
    assert wrong["ok"] is False
    assert wrong["error"] == "invalid_credentials"


def test_signup_persists_across_store_reload():
    auth.signup("newuser", PASSWORD, SIGNUP_CODE)
    auth.reset_state()  # 서버 재시작과 동일 — 스토어를 파일에서 다시 읽게 한다.

    assert auth.login("newuser", PASSWORD)["ok"] is True


def test_signup_duplicate_username_rejected():
    assert auth.signup("newuser", PASSWORD, SIGNUP_CODE)["ok"] is True
    duplicate = auth.signup("newuser", "another-password", SIGNUP_CODE)
    assert duplicate == {"ok": False, "error": "username_taken"}


def test_signup_cannot_shadow_bootstrap_account(monkeypatch):
    monkeypatch.setenv("DESKAD_LOGIN_ID", "deskad")
    monkeypatch.setenv("DESKAD_LOGIN_PASSWORD_SHA256", "0" * 64)
    result = auth.signup("deskad", PASSWORD, SIGNUP_CODE)
    assert result == {"ok": False, "error": "username_taken"}


def test_signup_wrong_or_missing_code(monkeypatch):
    wrong = auth.signup("newuser", PASSWORD, "wrong-code")
    assert wrong == {"ok": False, "error": "invalid_signup_code"}

    monkeypatch.delenv("DESKAD_SIGNUP_CODE")
    disabled = auth.signup("newuser", PASSWORD, SIGNUP_CODE)
    assert disabled == {"ok": False, "error": "signup_disabled"}


def test_signup_validation_error_codes():
    assert auth.signup("ab", PASSWORD, SIGNUP_CODE)["error"] == "invalid_username"
    assert auth.signup("newuser", "short", SIGNUP_CODE)["error"] == "weak_password"


def test_signup_endpoint_rejects_short_password_with_422(client):
    response = client.post(
        "/auth/signup",
        json={"username": "newuser", "password": "short", "signup_code": SIGNUP_CODE},
    )
    assert response.status_code == 422


# --- 다중 사용자 동작 ---

def test_lockout_is_per_username():
    auth.signup("alice", PASSWORD, SIGNUP_CODE)
    auth.signup("bob", PASSWORD, SIGNUP_CODE)

    now = 1_000.0
    for _ in range(5):
        auth.login("alice", "wrong", now=now)
    assert auth.login("alice", PASSWORD, now=now + 1)["error"] == "locked"
    # alice의 잠금이 bob에게 번지지 않는다.
    assert auth.login("bob", PASSWORD, now=now + 1)["ok"] is True


def test_login_unknown_user_with_signups_is_invalid_not_unconfigured():
    auth.signup("newuser", PASSWORD, SIGNUP_CODE)
    result = auth.login("ghost", PASSWORD)
    assert result["error"] == "invalid_credentials"
