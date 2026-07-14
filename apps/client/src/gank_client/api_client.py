from __future__ import annotations

import json
import logging

import httpx

from gank_client.config import (
    API_BASE,
    CONFIG_DIR,
    DEFAULT_REGION_ID,
    DEFAULT_REGION_NAME,
    SETTINGS_FILE,
    TOKEN_FILE,
)

logger = logging.getLogger("gank_client.api")


class ApiClient:
    def __init__(self) -> None:
        self._client = httpx.Client(base_url=API_BASE, timeout=10.0)
        self.api_token: str | None = None
        self.character_id: int | None = None
        self.character_name: str | None = None
        self._load_saved_token()

        self.region_id: int = DEFAULT_REGION_ID
        self.region_name: str = DEFAULT_REGION_NAME
        self._load_saved_region()

    def _load_saved_token(self) -> None:
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            self.api_token = data.get("api_token")
            self.character_id = data.get("character_id")
            self.character_name = data.get("character_name")

    def save_login(self, api_token: str, character_id: int, character_name: str) -> None:
        self.api_token = api_token
        self.character_id = character_id
        self.character_name = character_name
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(
            json.dumps(
                {"api_token": api_token, "character_id": character_id, "character_name": character_name}
            )
        )

    def logout(self) -> None:
        self.api_token = None
        self.character_id = None
        self.character_name = None
        TOKEN_FILE.unlink(missing_ok=True)

    @property
    def is_logged_in(self) -> bool:
        return self.api_token is not None

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_token}"}

    def _load_saved_region(self) -> None:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text())
            self.region_id = data.get("region_id", DEFAULT_REGION_ID)
            self.region_name = data.get("region_name", DEFAULT_REGION_NAME)

    def set_region(self, region_id: int, region_name: str) -> None:
        """Region is a purely local client preference -- api is region-
        agnostic and just serves whatever region_id each request asks for,
        so there's nothing to sync server-side here."""
        self.region_id = region_id
        self.region_name = region_name
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps({"region_id": region_id, "region_name": region_name}))

    def get_feed(self, limit: int = 50) -> list[dict]:
        resp = self._client.get("/feed", params={"region_id": self.region_id, "limit": limit})
        resp.raise_for_status()
        return resp.json()

    def get_my_location(self) -> dict | None:
        if not self.is_logged_in:
            return None
        resp = self._client.get("/me/location", headers=self._auth_headers())
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_jump_distance(self, from_system_id: int, to_system_id: int) -> int | None:
        resp = self._client.get(
            "/jump-distance",
            params={"from_system_id": from_system_id, "to_system_id": to_system_id},
        )
        if resp.status_code != 200:
            return None
        return resp.json()["jumps"]
