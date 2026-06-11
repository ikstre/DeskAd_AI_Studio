"""이 파일은 로그인/회원가입 페이지와 인증 게이트 helper를 담당한다."""

from __future__ import annotations

import re
import time

import streamlit as st

from .api_client import api_login, api_logout, api_signup

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")
PASSWORD_MIN_LENGTH = 8


def token_state_is_valid(token: object, expires_at: object, *, now: float | None = None) -> bool:
    """세션 토큰 보유 + 만료 전인지 판정하는 순수 함수(테스트 대상)."""
    if not isinstance(token, str) or not token:
        return False
    if expires_at is None:
        return True
    try:
        expiry = float(expires_at)
    except (TypeError, ValueError):
        return False
    now = time.time() if now is None else now
    return now < expiry


def is_authenticated() -> bool:
    """현재 세션이 로그인 상태인지 반환한다."""
    return token_state_is_valid(
        st.session_state.get("auth_token"),
        st.session_state.get("auth_expires_at"),
    )


def _store_login_success(result: dict, fallback_name: str) -> None:
    st.session_state.auth_token = result["token"]
    st.session_state.auth_display_name = result.get("display_name") or fallback_name
    st.session_state.auth_expires_at = result.get("expires_at")
    st.session_state.login_fail_count = 0


def _login_error_message(result: dict) -> str:
    """실패 사유를 사용자 안내 문구로 바꾼다 — 아이디/비밀번호 구분 노출 금지."""
    error = result.get("error")
    if error == "locked":
        retry_after = result.get("retry_after_seconds") or 60
        return f"로그인 시도가 잠시 제한되었습니다. {retry_after}초 후 다시 시도해주세요."
    if error == "not_configured":
        return "로그인이 아직 설정되지 않았습니다. 관리자에게 문의해주세요."
    if error == "request_failed":
        return "로그인 서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
    return "아이디 또는 비밀번호가 올바르지 않습니다."


def _signup_error_message(result: dict) -> str:
    error = result.get("error")
    if error == "signup_disabled":
        return "회원가입이 비활성화되어 있습니다. 관리자에게 문의해주세요."
    if error == "invalid_signup_code":
        return "가입 코드가 올바르지 않습니다."
    if error == "invalid_username":
        return "아이디는 3~32자의 영문/숫자/밑줄(_)/하이픈(-)만 사용할 수 있습니다."
    if error == "weak_password":
        return f"비밀번호는 {PASSWORD_MIN_LENGTH}자 이상이어야 합니다."
    if error == "username_taken":
        return "이미 사용 중인 아이디입니다."
    if error == "request_failed":
        return "서버에 연결할 수 없습니다. 잠시 후 다시 시도해주세요."
    return "회원가입에 실패했습니다. 입력값을 확인해주세요."


def _render_login_form() -> None:
    with st.form("login_form"):
        username = st.text_input("아이디", autocomplete="username")
        password = st.text_input("비밀번호", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("로그인", use_container_width=True, type="primary")

    if not submitted:
        return
    username = username.strip()
    if not username or not password:
        st.error("아이디와 비밀번호를 모두 입력해주세요.")
        return

    result = api_login(username, password)
    if result.get("ok") and result.get("token"):
        _store_login_success(result, username)
        st.rerun()
    st.session_state.login_fail_count = int(st.session_state.get("login_fail_count") or 0) + 1
    st.error(_login_error_message(result))


def _render_signup_form() -> None:
    with st.form("signup_form"):
        username = st.text_input("아이디", help="3~32자, 영문/숫자/밑줄(_)/하이픈(-)")
        password = st.text_input(
            "비밀번호", type="password", help=f"{PASSWORD_MIN_LENGTH}자 이상",
            autocomplete="new-password",
        )
        password_confirm = st.text_input("비밀번호 확인", type="password", autocomplete="new-password")
        signup_code = st.text_input("가입 코드", type="password", help="관리자에게 받은 코드를 입력하세요.")
        submitted = st.form_submit_button("회원가입", use_container_width=True, type="primary")

    if not submitted:
        return
    username = username.strip()
    if not username or not password or not password_confirm or not signup_code.strip():
        st.error("모든 항목을 입력해주세요.")
        return
    if not USERNAME_PATTERN.fullmatch(username):
        st.error(_signup_error_message({"error": "invalid_username"}))
        return
    if len(password) < PASSWORD_MIN_LENGTH:
        st.error(_signup_error_message({"error": "weak_password"}))
        return
    if password != password_confirm:
        st.error("비밀번호 확인이 일치하지 않습니다.")
        return

    result = api_signup(username, password, signup_code.strip())
    if result.get("ok") and result.get("token"):
        # 가입 즉시 자동 로그인.
        _store_login_success(result, username)
        st.rerun()
    st.error(_signup_error_message(result))


def render_login_page() -> None:
    """중앙 카드형 로그인/회원가입 페이지를 렌더링한다."""
    st.markdown("<div style='height: 10vh'></div>", unsafe_allow_html=True)
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.markdown(
            "<h2 style='text-align:center; margin-bottom: 0.2rem;'>DeskAd AI Studio</h2>"
            "<p style='text-align:center; color: #6b7280; margin-bottom: 1.2rem;'>"
            "로그인 후 스튜디오를 사용할 수 있습니다.</p>",
            unsafe_allow_html=True,
        )
        login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
        with login_tab:
            _render_login_form()
        with signup_tab:
            _render_signup_form()


def logout() -> None:
    """서버 세션 무효화 후 로컬 인증 상태를 비우고 로그인 화면으로 돌아간다."""
    token = st.session_state.get("auth_token")
    if token:
        api_logout(token)
    st.session_state.auth_token = None
    st.session_state.auth_display_name = None
    st.session_state.auth_expires_at = None
    st.rerun()
