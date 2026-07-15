from __future__ import annotations

import time

from gank_shared.models import GankEvent

RECHECK_DELAY_SECONDS = 180
"""How long to wait before re-checking a highsec kill that didn't have
zKillboard's "ganked" label on first read. zKillboard appears to add it
asynchronously -- likely correlating the victim's kill with CONCORD
killing the attacker, which itself takes anywhere from seconds to a few
minutes to show up in their pipeline. A single-pass R2Z2 read structurally
can't see labels added after the fact, confirmed in production: two real
ganks were missed on first read and had "ganked" present minutes later."""


class RecheckQueue:
    """Holds highsec-but-not-yet-"ganked" kills for a single delayed
    recheck. Single-shot by design -- an item is popped (and forgotten)
    the first time it's due, not polled repeatedly, to keep this bounded
    and simple."""

    def __init__(self, delay_seconds: float = RECHECK_DELAY_SECONDS) -> None:
        self.delay_seconds = delay_seconds
        self._items: dict[int, tuple[GankEvent, float]] = {}

    def add(self, event: GankEvent) -> None:
        self._items[event.killmail_id] = (event, time.monotonic())

    def pop_due(self) -> list[GankEvent]:
        now = time.monotonic()
        due_ids = [
            killmail_id
            for killmail_id, (_, added_at) in self._items.items()
            if now - added_at >= self.delay_seconds
        ]
        return [self._items.pop(killmail_id)[0] for killmail_id in due_ids]

    def __len__(self) -> int:
        return len(self._items)
