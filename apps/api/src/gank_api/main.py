from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gank_api import storage
from gank_api.auth import resolve_token
from gank_api.auth import router as auth_router
from gank_api.config import settings

app = FastAPI(title="gank-alert api")
app.include_router(auth_router)

bearer = HTTPBearer()


def current_character(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> tuple[int, str]:
    return resolve_token(creds.credentials)


@app.post("/location")
def post_location(
    solar_system_id: int,
    character: tuple[int, str] = Depends(current_character),
) -> dict:
    character_id, _ = character
    conn = storage.connect(settings.db_path)
    try:
        conn.execute(
            "INSERT INTO character_locations (character_id, solar_system_id, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(character_id) DO UPDATE SET solar_system_id = excluded.solar_system_id, "
            "updated_at = excluded.updated_at",
            (character_id, solar_system_id, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@app.get("/feed")
def get_feed(limit: int = 50) -> list[dict]:
    conn = storage.connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT payload_json FROM gank_events WHERE region_id = ? "
            "ORDER BY occurred_at DESC LIMIT ?",
            (settings.region_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


@app.get("/jump-distance")
def jump_distance(from_system_id: int, to_system_id: int) -> dict:
    # Needs the static stargate graph (ESI /universe/systems/*/stargates or
    # the SDE) for a shortest-path search -- not built yet.
    raise HTTPException(501, "jump-distance needs the static stargate graph, not implemented yet")


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
