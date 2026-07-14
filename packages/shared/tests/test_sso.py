import base64
import hashlib
import json

from gank_shared.sso import build_authorize_url, decode_unverified_jwt, new_pkce_challenge


def test_pkce_challenge_is_sha256_of_verifier():
    pkce = new_pkce_challenge()

    digest = hashlib.sha256(pkce.verifier.encode()).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    assert pkce.challenge == expected_challenge
    assert pkce.verifier and pkce.state
    assert pkce.verifier != pkce.state


def test_pkce_challenges_are_unique():
    a = new_pkce_challenge()
    b = new_pkce_challenge()
    assert a.verifier != b.verifier
    assert a.state != b.state


def test_build_authorize_url_contains_pkce_params():
    pkce = new_pkce_challenge()
    url = build_authorize_url(
        client_id="abc123",
        redirect_uri="https://example.com/callback",
        scopes=["esi-location.read_location.v1"],
        pkce=pkce,
    )

    assert url.startswith("https://login.eveonline.com/v2/oauth/authorize?")
    assert "client_id=abc123" in url
    assert f"state={pkce.state}" in url
    assert f"code_challenge={pkce.challenge}" in url
    assert "code_challenge_method=S256" in url


def _fake_jwt(payload: dict) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "RS256"}).encode())
    body = b64(json.dumps(payload).encode())
    return f"{header}.{body}.fake-signature"


def test_decode_unverified_jwt_reads_character_claims():
    token = _fake_jwt({"sub": "CHARACTER:EVE:12345", "name": "Aiko Danuja"})
    claims = decode_unverified_jwt(token)

    assert claims["sub"] == "CHARACTER:EVE:12345"
    assert claims["name"] == "Aiko Danuja"
