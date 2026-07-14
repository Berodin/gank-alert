"""Shared alert-staleness tiers -- used by both the bot (embed color/label)
and the client (feed row color/label, notification sound) so a kill is
categorized identically everywhere instead of two divergent systems."""

from __future__ import annotations

FRESH_MINUTES = 60
RECENT_MINUTES = 120
WARY_MINUTES = 240

# (age ceiling in minutes, label, hex color) -- hex works directly as both
# a Qt color string and (parsed) a discord.Color. STAY WARY is deliberately
# a desaturated gray-blue rather than another warm tone: in a thin 3px feed
# strip, orange vs. gold read as "the same color" at a glance -- fading to
# gray reads unambiguously as "this is aging out."
#
# Labeled FRESH, not IMMINENT -- this tier means the kill already
# happened moments ago, not that one is about to.
TIERS: list[tuple[int, str, str]] = [
    (FRESH_MINUTES, "FRESH", "#e74c3c"),
    (RECENT_MINUTES, "RECENT", "#e67e22"),
    (WARY_MINUTES, "STAY WARY", "#7f8c8d"),
]


def tier_for_age(age_minutes: float) -> tuple[str, str] | None:
    """Returns (label, hex_color), or None once past the alert window."""
    for max_minutes, label, color in TIERS:
        if age_minutes < max_minutes:
            return label, color
    return None
