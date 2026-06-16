"""이 파일은 UI 표시용 값 포맷팅 helper를 담당한다."""

from __future__ import annotations


def format_price_display(value: object, fallback: str = "가격 미입력") -> str:
    """판매가를 화면 표시용 콤마 숫자로 정리한다."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return fallback
    return f"{int(digits):,}"
