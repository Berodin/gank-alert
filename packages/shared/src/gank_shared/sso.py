"""EVE SSO OAuth2 PKCE (public client, no client secret) helpers.

Flow: https://developers.eveonline.com/docs/services/sso/
PKCE means no client secret is needed, which is required here since the
authorization code is exchanged by our own backend on behalf of desktop
app users -- there is no way to keep a secret safe in a distributed
desktop client, so EVE's SSO supports the public-client PKCE variant
instead (same approach lizard-intel's client uses).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass

import httpx

AUTHORIZE_URL = "https://login.eveonline.com/v2/oauth/authorize"
TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"
JWKS_ISSUER = "https://login.eveonline.com"


@dataclass
class PKCEChallenge:
    verifier: str
    challenge: str
    state: str


def new_pkce_challenge() -> PKCEChallenge:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    return PKCEChallenge(verifier=verifier, challenge=challenge, state=state)


def decode_unverified_jwt(access_token: str) -> dict:
    """Decode the JWT payload without verifying the signature, to read the
    character id/name (`sub` = "CHARACTER:EVE:<id>", `name`). Fine for our
    purposes since the token itself was just received directly from EVE's
    token endpoint over TLS -- we're not accepting arbitrary JWTs from
    untrusted callers. Swap for full JWKS verification if that changes.
    """
    import json

    payload_b64 = access_token.split(".")[1]
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def refresh_access_token(*, client_id: str, refresh_token: str) -> dict:
    """Exchange a refresh token for a new access token + refresh token.

    EVE SSO rotates the refresh token on every use -- the old one is
    invalidated, so the caller MUST persist the new refresh_token from the
    response or the character will need to log in again once the old
    access token expires (~20 min).
    """
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def build_authorize_url(*, client_id: str, redirect_uri: str, scopes: list[str], pkce: PKCEChallenge) -> str:
    from urllib.parse import urlencode

    params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "scope": " ".join(scopes),
        "state": pkce.state,
        "code_challenge": pkce.challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"
