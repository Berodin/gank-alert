import hashlib
from pathlib import Path

import pytest

from gank_api import storage
from gank_api.auth import _is_safe_loopback, resolve_token
from gank_api.config import settings


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://127.0.0.1:54321/callback", True),
        ("http://localhost:8080/x", True),
        ("http://evil.example.com/steal?fake=127.0.0.1", False),
        ("https://127.0.0.1:1234/callback", False),  # scheme must be http, not https
        ("http://127.0.0.1.evil.com:1234/", False),
    ],
)
def test_is_safe_loopback(url: str, expected: bool):
    assert _is_safe_loopback(url) is expected


def test_resolve_token_returns_character_for_valid_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "db.sqlite3")
    conn = storage.connect(settings.db_path)
    token_hash = hashlib.sha256(b"my-token").hexdigest()
    conn.execute(
        "INSERT INTO api_tokens (token_hash, character_id, character_name, eve_access_token, eve_refresh_token, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (token_hash, 42, "Aiko Danuja", "x", "y", "now"),
    )
    conn.commit()
    conn.close()

    character_id, character_name = resolve_token("my-token")
    assert character_id == 42
    assert character_name == "Aiko Danuja"


def test_resolve_token_rejects_unknown_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "db.sqlite3")
    storage.connect(settings.db_path).close()  # create empty db

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        resolve_token("not-a-real-token")
    assert exc_info.value.status_code == 401
