from __future__ import annotations

import time

from gank_shared.models import GankEvent

RECHECK_INTERVALS_SECONDS = [180, 300]
"""Retry schedule for re-checking a highsec kill that didn't have
zKillboard's "ganked" label on first read: first check 180s after it's
queued, and if still nothing, one more check 300s after that (~8 minutes
total) before giving up. zKillboard appears to add the label
asynchronously -- likely correlating the victim's kill with CONCORD
killing the attacker(s), which itself takes anywhere from seconds to
several minutes. A single 180s check was not resilient enough: confirmed
in production on large multi-attacker (10+) fleet ganks, where presumably
correlating that many attacker deaths against CONCORD takes longer than
simpler ganks -- those still had no "ganked" label at the 180s mark but
did within the following few minutes."""


class RecheckQueue:
    """Holds highsec-but-not-yet-"ganked" kills for a bounded number of
    delayed rechecks (see RECHECK_INTERVALS_SECONDS), not indefinite
    polling -- each item gets at most len(intervals) attempts before
    being dropped for good."""

    def __init__(self, intervals: list[float] = RECHECK_INTERVALS_SECONDS) -> None:
        self.intervals = intervals
        # killmail_id -> (event, due_at, attempt_index)
        self._items: dict[int, tuple[GankEvent, float, int]] = {}

    def add(self, event: GankEvent) -> None:
        if event.killmail_id in self._items:
            return  # already queued, don't reset its schedule
        self._items[event.killmail_id] = (event, time.monotonic() + self.intervals[0], 0)

    def pop_due(self) -> list[tuple[GankEvent, int]]:
        """Returns (event, attempt_index) for items whose current wait has
        elapsed, removing them from the queue. Call reschedule() on ones
        that still aren't "ganked" to queue the next attempt, if any
        remain -- otherwise the item is gone for good."""
        now = time.monotonic()
        due_ids = [
            killmail_id for killmail_id, (_, due_at, _) in self._items.items() if now >= due_at
        ]
        return [
            (event, attempt) for killmail_id in due_ids for event, _, attempt in [self._items.pop(killmail_id)]
        ]

    def reschedule(self, event: GankEvent, attempt: int) -> bool:
        """Returns False (and drops the item) if retries are exhausted."""
        next_attempt = attempt + 1
        if next_attempt >= len(self.intervals):
            return False
        self._items[event.killmail_id] = (
            event,
            time.monotonic() + self.intervals[next_attempt],
            next_attempt,
        )
        return True

    def __len__(self) -> int:
        return len(self._items)
