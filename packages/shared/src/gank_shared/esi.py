from __future__ import annotations

import logging
import time

import httpx

from gank_shared.user_agent import build_user_agent

logger = logging.getLogger(__name__)

ESI_BASE = "https://esi.evetech.net/latest"


class ESIClient:
    """Minimal rate-limit-aware ESI client.

    Only implements what gank-alert needs: static universe lookups
    (system -> constellation -> region) and killmail verification.
    Static data is cached forever in-process since it never changes.
    """

    def __init__(self, component: str, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=ESI_BASE,
            timeout=20.0,
            headers={"User-Agent": build_user_agent(component)},
        )
        self._system_region_cache: dict[int, int] = {}
        self._constellation_region_cache: dict[int, int] = {}
        self._system_name_cache: dict[int, str] = {}
        self._error_cooldown_until: float = 0.0

    def close(self) -> None:
        self._client.close()

    def _get(self, path: str, *, access_token: str | None = None) -> httpx.Response:
        if (wait := self._error_cooldown_until - time.monotonic()) > 0:
            logger.warning("ESI error budget exhausted, sleeping %.1fs", wait)
            time.sleep(wait)

        headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        resp = self._client.get(path, headers=headers)

        remain = resp.headers.get("X-Esi-Error-Limit-Remain")
        reset = resp.headers.get("X-Esi-Error-Limit-Reset")
        if remain is not None and int(remain) < 10 and reset is not None:
            self._error_cooldown_until = time.monotonic() + int(reset)

        if resp.status_code == 420:
            retry_after = float(resp.headers.get("Retry-After", "60"))
            self._error_cooldown_until = time.monotonic() + retry_after
            raise httpx.HTTPStatusError(
                "ESI error-limited (420)", request=resp.request, response=resp
            )

        resp.raise_for_status()
        return resp

    def region_id_for_system(self, solar_system_id: int) -> int:
        if solar_system_id in self._system_region_cache:
            return self._system_region_cache[solar_system_id]

        system = self._get(f"/universe/systems/{solar_system_id}/").json()
        constellation_id = system["constellation_id"]
        self._system_name_cache[solar_system_id] = system["name"]

        region_id = self._constellation_region_cache.get(constellation_id)
        if region_id is None:
            constellation = self._get(f"/universe/constellations/{constellation_id}/").json()
            region_id = constellation["region_id"]
            self._constellation_region_cache[constellation_id] = region_id

        self._system_region_cache[solar_system_id] = region_id
        return region_id

    def system_name(self, solar_system_id: int) -> str:
        if solar_system_id not in self._system_name_cache:
            system = self._get(f"/universe/systems/{solar_system_id}/").json()
            self._system_name_cache[solar_system_id] = system["name"]
        return self._system_name_cache[solar_system_id]

    def get_killmail(self, killmail_id: int, killmail_hash: str) -> dict:
        """Fetch the authoritative killmail directly from ESI (public, no auth).

        Not used by default -- R2Z2 already embeds the raw ESI killmail --
        but kept for spot-verification.
        """
        return self._get(f"/killmails/{killmail_id}/{killmail_hash}/").json()

    def get_character_location(self, character_id: int, access_token: str) -> dict:
        """Requires the esi-location.read_location.v1 scope on access_token."""
        return self._get(f"/characters/{character_id}/location/", access_token=access_token).json()
