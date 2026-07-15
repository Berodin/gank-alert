"""zKillboard's REST API -- used only to re-check a single killmail's
current zkb.labels after a delay. Discovery itself goes through R2Z2
(see gank_ingester.r2z2); this is a narrow, low-volume supplement for the
fact that zKillboard adds labels like "ganked" asynchronously, sometimes
after our one-pass R2Z2 read has already moved on (it looks like it needs
to correlate the victim's kill with CONCORD killing the attacker, which
itself takes a few seconds to minutes to show up).

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
        resp = client.get(f"{BASE}/killID/{killmail_id}/")
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
