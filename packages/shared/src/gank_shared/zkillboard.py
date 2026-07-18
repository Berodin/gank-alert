"""zKillboard's REST API -- used only as a fallback safety net for a
single killmail's current zkb.labels, behind gank_ingester.recheck.
Primary detection of retroactively-added labels (e.g. "ganked") goes
through R2Z2's `sequence_updated` pointer (see main.py), which fires
precisely when zKillboard relabels a kill -- confirmed against
zKillboard's own source (cron/9.ganked.php) and wiki ("API (R2Z2)"). This
REST poll only runs for kills where that signal was somehow missed.

Per https://github.com/zKillboard/zKillboard/wiki/API-(Killmails): be
polite, send a User-Agent, don't hammer. This is called sparingly -- only
for kills genuinely pending a recheck, not as a discovery mechanism.
"""

from __future__ import annotations

import httpx

from gank_shared.user_agent import build_user_agent

BASE = "https://zkillboard.com/api"


def fetch_current_labels(killmail_id: int, *, client: httpx.Client | None = None) -> list[str]:
    """Returns the killmail's current zkb.labels, or [] if it can't be
    fetched (not found, transient error -- callers should treat that as
    "still nothing new" rather than an error worth raising)."""
    owns_client = client is None
    client = client or httpx.Client(
        timeout=15.0, headers={"User-Agent": build_user_agent("ingester-recheck")}
    )
    try:
        # killID is documented as a modifier combined with a /kills/ (or
        # /losses/) prefix, not a standalone endpoint -- the bare
        # /api/killID/{id}/ shortcut appears to hit a staler cache and
        # returns [] for recently-created kills, confirmed in production
        # against a real kill that had "ganked" via this path but not that
        # one. Always use the documented /kills/killID/ form.
        resp = client.get(f"{BASE}/kills/killID/{killmail_id}/")
        if resp.status_code != 200:
            return []
        rows = resp.json()
        if not rows:
            return []
        return rows[0].get("zkb", {}).get("labels", [])
    except httpx.HTTPError:
        return []
    finally:
        if owns_client:
            client.close()
