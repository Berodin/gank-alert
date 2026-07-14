"""Static system-adjacency graph (stargate connections only, no jump
bridges/wormholes) for shortest-path jump-distance queries.

This is static game data -- it changes maybe once or twice a year with
expansions. Build it once with build_graph() and ship the resulting JSON;
don't rebuild it on every deploy.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from pathlib import Path

import httpx

from gank_shared.user_agent import build_user_agent

logger = logging.getLogger(__name__)

ESI_BASE = "https://esi.evetech.net/latest"


async def _fetch_json(client: httpx.AsyncClient, sem: asyncio.Semaphore, path: str) -> dict | None:
    async with sem:
        resp = await client.get(path)
        if resp.status_code != 200:
            logger.warning("skip %s: HTTP %d", path, resp.status_code)
            return None
        return resp.json()


async def build_graph_async(output_path: Path, concurrency: int = 30) -> None:
    async with httpx.AsyncClient(
        base_url=ESI_BASE,
        timeout=30.0,
        headers={"User-Agent": build_user_agent("universe-graph-builder")},
        limits=httpx.Limits(max_connections=concurrency + 10),
    ) as client:
        sem = asyncio.Semaphore(concurrency)

        system_ids: list[int] = await _fetch_json(client, sem, "/universe/systems/")
        logger.info("fetching details for %d systems", len(system_ids))

        systems = await asyncio.gather(
            *(_fetch_json(client, sem, f"/universe/systems/{sid}/") for sid in system_ids)
        )

        stargate_ids: set[int] = set()
        for system in systems:
            if system:
                stargate_ids.update(system.get("stargates", []))

        logger.info("fetching details for %d stargates", len(stargate_ids))
        stargates = await asyncio.gather(
            *(_fetch_json(client, sem, f"/universe/stargates/{gid}/") for gid in stargate_ids)
        )

        graph: dict[int, set[int]] = {}
        for gate in stargates:
            if not gate:
                continue
            a, b = gate["system_id"], gate["destination"]["system_id"]
            graph.setdefault(a, set()).add(b)
            graph.setdefault(b, set()).add(a)

        serializable = {str(k): sorted(v) for k, v in graph.items()}
        output_path.write_text(json.dumps(serializable))
        logger.info(
            "wrote %s: %d systems with at least one stargate connection", output_path, len(serializable)
        )


def build_graph(output_path: Path, concurrency: int = 30) -> None:
    asyncio.run(build_graph_async(output_path, concurrency=concurrency))


def load_graph(path: Path) -> dict[int, list[int]]:
    raw = json.loads(path.read_text())
    return {int(k): v for k, v in raw.items()}


def bfs_jump_distance(graph: dict[int, list[int]], from_system_id: int, to_system_id: int) -> int | None:
    """Fewest stargate jumps between two systems, or None if unreachable
    (e.g. one of them is wormhole space with no persistent gates)."""
    if from_system_id == to_system_id:
        return 0
    if from_system_id not in graph or to_system_id not in graph:
        return None

    visited = {from_system_id}
    queue = deque([(from_system_id, 0)])
    while queue:
        system_id, dist = queue.popleft()
        for neighbor in graph.get(system_id, []):
            if neighbor == to_system_id:
                return dist + 1
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, dist + 1))
    return None


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("universe_graph.json")
    build_graph(out)
