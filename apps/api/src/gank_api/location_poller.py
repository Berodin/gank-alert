from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from gank_shared.esi import ESIClient
from gank_shared.sso import refresh_access_token

from gank_api import storage
from gank_api.config import settings

logger = logging.getLogger("gank_api.location_poller")

POLL_INTERVAL_SECONDS = 60


async def _poll_once(esi: ESIClient) -> None:
    conn = storage.connect(settings.db_path)
    try:
        characters = conn.execute(
            "SELECT character_id, eve_refresh_token FROM api_tokens"
        ).fetchall()
    finally:
        conn.close()

    for character_id, refresh_token in characters:
        try:
            # EVE SSO rotates the refresh token on every use -- persist the
            # new one immediately or the character gets logged out.
            tokens = await asyncio.to_thread(
                refresh_access_token, client_id=settings.eve_client_id, refresh_token=refresh_token
            )
            location = await asyncio.to_thread(
                esi.get_character_location, character_id, tokens["access_token"]
            )

            conn = storage.connect(settings.db_path)
            try:
                conn.execute(
                    "UPDATE api_tokens SET eve_access_token = ?, eve_refresh_token = ? "
                    "WHERE character_id = ?",
                    (tokens["access_token"], tokens["refresh_token"], character_id),
                )
                conn.execute(
                    "INSERT INTO character_locations (character_id, solar_system_id, updated_at) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(character_id) DO UPDATE SET solar_system_id = excluded.solar_system_id, "
                    "updated_at = excluded.updated_at",
                    (character_id, location["solar_system_id"], datetime.now(UTC).isoformat()),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.exception("failed to poll location for character_id=%d", character_id)


async def run_forever() -> None:
    esi = ESIClient(component="api-location-poller")
    try:
        while True:
            await _poll_once(esi)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        esi.close()
