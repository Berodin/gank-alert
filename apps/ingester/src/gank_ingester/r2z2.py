from __future__ import annotations

import logging
import time
from collections.abc import Iterator

import httpx

from gank_shared.user_agent import build_user_agent

logger = logging.getLogger(__name__)

BASE = "https://r2z2.zkillboard.com/ephemeral"

# Per https://github.com/zKillboard/zKillboard/wiki/API-(R2Z2):
# rate limit is 15 req/s per IP, and callers must wait >=6s after a 404
# (average kill rate is ~1/5.5s, polling faster has no benefit).
MIN_INTERVAL_ON_404 = 6.0
MIN_INTERVAL_BETWEEN_HITS = 0.1


class R2Z2Client:
    def __init__(self) -> None:
        self._client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": build_user_agent("ingester")},
        )

    def close(self) -> None:
        self._client.close()

    def latest_sequence(self) -> int:
        resp = self._client.get(f"{BASE}/sequence.json")
        resp.raise_for_status()
        return resp.json()["sequence"]

    def fetch(self, sequence_id: int) -> dict | None:
        """Returns the killmail package, or None if not there (yet)."""
        resp = self._client.get(f"{BASE}/{sequence_id}.json")
        if resp.status_code == 404:
            return None
        if resp.status_code == 403:
            raise httpx.HTTPStatusError(
                "R2Z2 blocked us (403) -- check User-Agent / rate limiting",
                request=resp.request,
                response=resp,
            )
        resp.raise_for_status()
        return resp.json()

    def iter_from(self, start_sequence: int) -> Iterator[dict]:
        """Yields killmail packages forever, starting at start_sequence.

        Blocks (sleeps) internally to respect R2Z2's rate limit contract.
        """
        sequence = start_sequence
        while True:
            package = self.fetch(sequence)
            if package is None:
                logger.debug("sequence %d not ready, waiting %.0fs", sequence, MIN_INTERVAL_ON_404)
                time.sleep(MIN_INTERVAL_ON_404)
                continue

            yield package
            sequence += 1
            time.sleep(MIN_INTERVAL_BETWEEN_HITS)
