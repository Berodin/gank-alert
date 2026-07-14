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

# Sequence files are only guaranteed to live >=24h before R2 purges them.
# A 404 on a sequence we're resuming from (e.g. after downtime) is
# indistinguishable from "not produced yet" -- if we've been retrying the
# same sequence this long, assume it's gone rather than hang forever.
STUCK_TIMEOUT_SECONDS = 10 * 60
# ...but only jump forward if we're genuinely far behind (a real quiet
# period can also produce a 10-minute stall). This many sequences behind
# latest is roughly half an hour of kills at the long-run average rate.
STUCK_GAP_THRESHOLD = 300


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
        If start_sequence turns out to already be expired/purged (e.g. the
        ingester was down for a long time), a 404 on it looks identical to
        "not produced yet" -- without a way to tell them apart, we detect
        a long stall on a sequence far behind the live edge and jump
        forward to it, accepting the gap as lost rather than hanging.
        """
        sequence = start_sequence
        stuck_since: float | None = None

        while True:
            package = self.fetch(sequence)
            if package is None:
                now = time.monotonic()
                if stuck_since is None:
                    stuck_since = now
                elif now - stuck_since > STUCK_TIMEOUT_SECONDS:
                    latest = self.latest_sequence()
                    gap = latest - sequence
                    if gap > STUCK_GAP_THRESHOLD:
                        logger.warning(
                            "sequence %d looks expired (stuck %.0fs, %d behind latest %d) "
                            "-- jumping forward, accepting the gap as lost",
                            sequence,
                            now - stuck_since,
                            gap,
                            latest,
                        )
                        sequence = latest
                        stuck_since = None
                        continue
                    # gap is small -- genuinely just a quiet period, keep waiting.
                    stuck_since = now

                logger.debug("sequence %d not ready, waiting %.0fs", sequence, MIN_INTERVAL_ON_404)
                time.sleep(MIN_INTERVAL_ON_404)
                continue

            stuck_since = None
            yield package
            sequence += 1
            time.sleep(MIN_INTERVAL_BETWEEN_HITS)
