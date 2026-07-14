from __future__ import annotations

import hashlib
import secrets
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from gank_shared.sso import (
    TOKEN_URL,
    build_authorize_url,
    decode_unverified_jwt,
    new_pkce_challenge,
)

from gank_api import storage
from gank_api.config import settings

router = APIRouter(prefix="/auth/eve", tags=["auth"])

# state -> (verifier, return_to, created_at). TTL-expire on lookup;
# single-process only -- fine for now, move to the DB if the api ever runs
# with >1 worker.
_pending: dict[str, tuple[str, str | None, float]] = {}
_PENDING_TTL_SECONDS = 300


def _is_safe_loopback(url: str) -> bool:
    """return_to must point at the caller's own loopback listener -- never
    follow it otherwise, or a crafted login link could exfiltrate a freshly
    issued api_token to an attacker's server (open-redirect)."""
    return url.startswith("http://127.0.0.1:") or url.startswith("http://localhost:")


@router.get("/login")
def login(return_to: str | None = None) -> RedirectResponse:
    """return_to: optional http://127.0.0.1:<port>/... the desktop client
    is listening on. If set, /callback redirects the browser back there
    with the api_token instead of returning it as raw JSON."""
    if return_to is not None and not _is_safe_loopback(return_to):
        raise HTTPException(400, "return_to must be a loopback (127.0.0.1/localhost) URL")

    pkce = new_pkce_challenge()
    _pending[pkce.state] = (pkce.verifier, return_to, time.monotonic())
    url = build_authorize_url(
        client_id=settings.eve_client_id,
        redirect_uri=settings.eve_redirect_uri,
        scopes=settings.scopes,
        pkce=pkce,
    )
    return RedirectResponse(url)


@router.get("/callback")
def callback(code: str, state: str):
    pending = _pending.pop(state, None)
    if pending is None:
        raise HTTPException(400, "unknown or expired state")
    verifier, return_to, created_at = pending
    if time.monotonic() - created_at > _PENDING_TTL_SECONDS:
        raise HTTPException(400, "login expired, try again")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.eve_client_id,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    resp.raise_for_status()
    tokens = resp.json()

    claims = decode_unverified_jwt(tokens["access_token"])
    character_id = int(claims["sub"].removeprefix("CHARACTER:EVE:"))
    character_name = claims["name"]

    api_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(api_token.encode()).hexdigest()

    conn = storage.connect(settings.db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO api_tokens "
            "(token_hash, character_id, character_name, eve_access_token, eve_refresh_token, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                token_hash,
                character_id,
                character_name,
                tokens["access_token"],
                tokens["refresh_token"],
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if return_to is not None:
        from urllib.parse import urlencode

        params = urlencode(
            {"api_token": api_token, "character_id": character_id, "character_name": character_name}
        )
        return RedirectResponse(f"{return_to}?{params}")

    return {"api_token": api_token, "character_id": character_id, "character_name": character_name}


def resolve_token(api_token: str) -> tuple[int, str]:
    token_hash = hashlib.sha256(api_token.encode()).hexdigest()
    conn = storage.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT character_id, character_name FROM api_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(401, "invalid token")
    return row[0], row[1]
