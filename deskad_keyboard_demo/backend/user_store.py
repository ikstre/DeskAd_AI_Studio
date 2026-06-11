"""회원가입 사용자 영구 저장소(JSON 파일) — job_store와 같은 Lock+원자적 쓰기 패턴.

파일 형식: {username: record} 단일 JSON 객체. record에는 평문 비밀번호 대신
salt+PBKDF2 해시만 저장한다. 파일은 생성 시 0o600으로 잠근다.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path


class UserStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._cache: dict[str, dict] | None = None

    @property
    def path(self) -> Path:
        return self._path

    def _ensure_loaded(self) -> dict[str, dict]:
        if self._cache is None:
            self._cache = self._read_snapshot()
        return self._cache

    def _read_snapshot(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            username: record
            for username, record in payload.items()
            if isinstance(username, str) and isinstance(record, dict)
        }

    def _write_snapshot(self, snapshot: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix=".users_", suffix=".json.tmp", dir=str(self._path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def get(self, username: str) -> dict | None:
        with self._lock:
            record = self._ensure_loaded().get(username)
            return dict(record) if record else None

    def count(self) -> int:
        with self._lock:
            return len(self._ensure_loaded())

    def add(self, username: str, record: dict) -> bool:
        """사용자를 추가한다. 이미 존재하면 False(덮어쓰기 금지)."""
        with self._lock:
            snapshot = self._ensure_loaded()
            if username in snapshot:
                return False
            snapshot[username] = dict(record)
            self._write_snapshot(snapshot)
            return True
