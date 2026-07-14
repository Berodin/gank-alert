from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gank_shared.universe_graph import bfs_jump_distance, load_graph

from gank_api import storage
from gank_api.auth import resolve_token
from gank_api.auth import router as auth_router
from gank_api.config import settings
from gank_api.location_poller import run_forever as run_location_poller

logger = logging.getLogger("gank_api")

universe_graph: dict[int, list[int]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global universe_graph
    if settings.universe_graph_path.exists():
        universe_graph = load_graph(settings.universe_graph_path)
        logger.info("loaded universe graph: %d systems", len(universe_graph))
    else:
        logger.warning(
            "universe graph not found at %s -- /jump-distance will 501. "
            "Build it with: python -m gank_shared.universe_graph <path>",
            settings.universe_graph_path,
        )

    poller_task = asyncio.create_task(run_location_poller())
    try:
        yield
    finally:
        poller_task.cancel()


app = FastAPI(title="gank-alert api", lifespan=lifespan)
app.include_router(auth_router)

bearer = HTTPBearer()


def current_character(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> tuple[int, str]:
    return resolve_token(creds.credentials)


@app.get("/me/location")
def my_location(character: tuple[int, str] = Depends(current_character)) -> dict:
    character_id, _ = character
    conn = storage.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT solar_system_id, updated_at FROM character_locations WHERE character_id = ?",
            (character_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "no location known yet -- wait for the next poll cycle (~60s)")
    return {"solar_system_id": row[0], "updated_at": row[1]}


@app.get("/feed")
def get_feed(region_id: int, limit: int = 50) -> list[dict]:
    conn = storage.connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT payload_json FROM gank_events WHERE region_id = ? "
            "ORDER BY occurred_at DESC LIMIT ?",
            (region_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [json.loads(r[0]) for r in rows]


@app.get("/jump-distance")
def jump_distance(from_system_id: int, to_system_id: int) -> dict:
    if not universe_graph:
        raise HTTPException(501, "universe graph not loaded, see server logs")
    jumps = bfs_jump_distance(universe_graph, from_system_id, to_system_id)
    if jumps is None:
        raise HTTPException(404, "no stargate path between those systems")
    return {"jumps": jumps}


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
