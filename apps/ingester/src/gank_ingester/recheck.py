from __future__ import annotations

import time

from gank_shared.models import GankEvent

RECHECK_INTERVALS_SECONDS = [600, 960]
"""Fallback retry schedule for re-checking a highsec kill that didn't have
zKillboard's "ganked" label on first read.

This is a safety net, not the primary mechanism -- the primary path is
main.py reacting to the R2Z2 `sequence_updated` pointer (see
zKillboard's own wiki, "API (R2Z2)"), which fires precisely when
zKillboard retroactively relabels a kill. This REST-polling fallback
exists only in case that signal is missed (e.g. an ingester restart gap).

The timing here is not a guess: read directly from zKillboard's own
source (cron/9.ganked.php), "ganked" is added by a batch job that
correlates the victim's kill with CONCORD killing the attacker(s), and
that job self-throttles to run at most once every 900 seconds (15
minutes) -- so a kill can legitimately need just under 900s before the
next run even attempts it. First check at 600s catches the common case
where a run happens to land early; the second at 960s clears the full
900s worst case plus margin. Beyond that, only zKillboard's own daily
full-history sweep (cron/9.ganked_full.php, ~once per 25h) would still
catch it -- not worth polling further for."""


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
