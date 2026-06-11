"""deskad 로그인/회원가입과 메모리 세션을 담당한다.

- 계정 출처는 두 갈래: ① 가입 사용자(data/runtime/users.json, salt+PBKDF2 해시)
  ② .env 부트스트랩 운영 계정(DESKAD_LOGIN_ID / DESKAD_LOGIN_PASSWORD_SHA256, 평문 금지).
- 회원가입은 .env의 DESKAD_SIGNUP_CODE를 아는 사람만 가능(미설정이면 가입 비활성).
- 비교는 secrets.compare_digest 상수시간 비교만 사용한다.
- 세션은 서버 메모리 dict[token, record] + TTL — 단일 인스턴스 운영이라 충분하며,
  job_store와 같은 이유로 Lock으로 보호한다(2026-06-11 QA 동시성 교훈).
- 연속 실패 잠금: 계정별 LOCKOUT_THRESHOLD회 실패 시 LOCKOUT_SECONDS 동안 정답도 거부.
"""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
import time
from pathlib import Path

from .user_store import UserStore

SESSION_TTL_SECONDS = 12 * 3600
LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 60.0
PBKDF2_ITERATIONS = 200_000
PASSWORD_MIN_LENGTH = 8
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_USERS_PATH = BASE_DIR / "data" / "runtime" / "users.json"

_LOCK = threading.Lock()
# token -> {"username": str, "issued_at": float, "expires_at": float}
_SESSIONS: dict[str, dict] = {}
# username -> {"count": int, "locked_until": float}
_FAIL_STATES: dict[str, dict] = {}
_USER_STORE: UserStore | None = None


def user_store() -> UserStore:
    """가입 사용자 저장소 — 경로는 DESKAD_USERS_PATH로 재지정 가능(테스트용)."""
    global _USER_STORE
    if _USER_STORE is None:
        path = Path(os.getenv("DESKAD_USERS_PATH", str(DEFAULT_USERS_PATH)))
        _USER_STORE = UserStore(path)
    return _USER_STORE


def _configured_credentials() -> tuple[str, str]:
    """환경 변수에서 부트스트랩 운영 계정(아이디, 비밀번호 SHA256)을 읽는다.

    Settings는 lru_cache로 고정되므로 거치지 않고 매 호출 os.getenv로 읽는다 —
    테스트(monkeypatch)와 .env 갱신 후 재기동 시점 차이를 줄인다.
    """
    login_id = os.getenv("DESKAD_LOGIN_ID", "").strip()
    password_sha256 = os.getenv("DESKAD_LOGIN_PASSWORD_SHA256", "").strip().lower()
    return login_id, password_sha256


def _pbkdf2_hex(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


def _verify_user_record(record: dict, password: str) -> bool:
    salt_hex = record.get("salt", "")
    stored_hash = record.get("password_pbkdf2", "")
    iterations = int(record.get("iterations") or PBKDF2_ITERATIONS)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if not salt or not stored_hash:
        return False
    return secrets.compare_digest(_pbkdf2_hex(password, salt, iterations), stored_hash)


def _verify_bootstrap_account(username: str, password: str) -> bool:
    login_id, password_sha256 = _configured_credentials()
    if not login_id or not password_sha256:
        return False
    provided_sha256 = hashlib.sha256(password.encode("utf-8")).hexdigest()
    username_ok = secrets.compare_digest(username.encode("utf-8"), login_id.encode("utf-8"))
    password_ok = secrets.compare_digest(provided_sha256, password_sha256)
    return username_ok and password_ok


def _prune_expired(now: float) -> None:
    expired = [token for token, record in _SESSIONS.items() if record["expires_at"] <= now]
    for token in expired:
        _SESSIONS.pop(token, None)


def _issue_session(username: str, now: float) -> dict:
    """_LOCK을 잡은 상태에서 호출한다."""
    _prune_expired(now)
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = {
        "username": username,
        "issued_at": now,
        "expires_at": now + SESSION_TTL_SECONDS,
    }
    return {
        "ok": True,
        "token": token,
        "display_name": username,
        "expires_at": _SESSIONS[token]["expires_at"],
    }


def login(username: str, password: str, *, now: float | None = None) -> dict:
    """자격증명을 검증하고 성공 시 세션 토큰을 발급한다.

    반환은 LoginResponse와 같은 형태의 dict:
    성공 {ok, token, display_name, expires_at} / 실패 {ok: False, error[, retry_after_seconds]}.
    """
    now = time.time() if now is None else now
    username = username.strip()

    login_id, password_sha256 = _configured_credentials()
    bootstrap_configured = bool(login_id and password_sha256)
    if not bootstrap_configured and user_store().count() == 0:
        # 로그인할 수 있는 계정이 하나도 없는 상태 — 설정 누락을 명확히 알린다.
        return {"ok": False, "error": "not_configured"}

    with _LOCK:
        fail_state = _FAIL_STATES.setdefault(username, {"count": 0, "locked_until": 0.0})
        locked_until = fail_state["locked_until"]
        if now < locked_until:
            return {
                "ok": False,
                "error": "locked",
                "retry_after_seconds": max(1, int(locked_until - now + 0.999)),
            }

        record = user_store().get(username)
        if record is not None:
            verified = _verify_user_record(record, password)
        else:
            verified = _verify_bootstrap_account(username, password)

        if not verified:
            fail_state["count"] += 1
            if fail_state["count"] >= LOCKOUT_THRESHOLD:
                fail_state["count"] = 0
                fail_state["locked_until"] = now + LOCKOUT_SECONDS
                return {
                    "ok": False,
                    "error": "locked",
                    "retry_after_seconds": int(LOCKOUT_SECONDS),
                }
            return {"ok": False, "error": "invalid_credentials"}

        fail_state["count"] = 0
        fail_state["locked_until"] = 0.0
        return _issue_session(username, now)


def signup(username: str, password: str, signup_code: str, *, now: float | None = None) -> dict:
    """가입 코드 검증 후 사용자를 등록하고 곧바로 세션을 발급한다(자동 로그인).

    실패 error 코드: signup_disabled | invalid_signup_code | invalid_username |
    weak_password | username_taken.
    """
    now = time.time() if now is None else now
    configured_code = os.getenv("DESKAD_SIGNUP_CODE", "").strip()
    if not configured_code:
        return {"ok": False, "error": "signup_disabled"}
    if not secrets.compare_digest(signup_code.encode("utf-8"), configured_code.encode("utf-8")):
        return {"ok": False, "error": "invalid_signup_code"}

    username = username.strip()
    if not USERNAME_PATTERN.fullmatch(username):
        return {"ok": False, "error": "invalid_username"}
    if len(password) < PASSWORD_MIN_LENGTH:
        return {"ok": False, "error": "weak_password"}

    login_id, _ = _configured_credentials()
    if login_id and username == login_id:
        return {"ok": False, "error": "username_taken"}

    salt = secrets.token_bytes(16)
    record = {
        "username": username,
        "password_pbkdf2": _pbkdf2_hex(password, salt, PBKDF2_ITERATIONS),
        "salt": salt.hex(),
        "iterations": PBKDF2_ITERATIONS,
        "created_at": now,
    }
    if not user_store().add(username, record):
        return {"ok": False, "error": "username_taken"}

    with _LOCK:
        return _issue_session(username, now)


def logout(token: str) -> bool:
    """세션 토큰을 무효화한다. 존재했던 토큰이면 True."""
    with _LOCK:
        return _SESSIONS.pop(token, None) is not None


def is_token_valid(token: str, *, now: float | None = None) -> bool:
    """토큰이 발급되어 있고 만료 전인지 확인한다."""
    if not token:
        return False
    now = time.time() if now is None else now
    with _LOCK:
        record = _SESSIONS.get(token)
        if record is None:
            return False
        if record["expires_at"] <= now:
            _SESSIONS.pop(token, None)
            return False
        return True


def reset_state() -> None:
    """세션/잠금/스토어 핸들 초기화 — 테스트 격리 용도."""
    global _USER_STORE
    with _LOCK:
        _SESSIONS.clear()
        _FAIL_STATES.clear()
        _USER_STORE = None
