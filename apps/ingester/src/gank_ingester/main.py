from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from gank_shared.esi import ESIClient
from gank_shared.ganker_list import load_ganker_list
from gank_shared.models import GankEvent, GankerListEntry
from gank_shared.zkillboard import fetch_current_labels

from gank_ingester import storage
from gank_ingester.parse import classify_gank, needs_gank_recheck, parse_package
from gank_ingester.r2z2 import R2Z2Client
from gank_ingester.recheck import RecheckQueue

logger = logging.getLogger("gank_ingester")

RECHECK_CALL_INTERVAL_SECONDS = 1.0
"""Minimum gap between successive zKillboard REST calls when processing a
batch of due rechecks. Without this, a burst of kills that all became due
around the same time (observed in production: up to 13 at once) fires
that many REST calls back to back with zero pacing -- confirmed some of
those get silently dropped (fetch_current_labels returns [] on any
non-200, indistinguishable from "genuinely not a gank"), almost certainly
zKillboard rate-limiting the burst."""


def _save_gank(
    conn, esi: ESIClient, event: GankEvent, matches: list[GankerListEntry], *, source: str
) -> None:
    event.region_id = esi.region_id_for_system(event.solar_system_id)
    event.is_gank = True
    event.matched_entities = matches
    storage.save_gank_event(conn, event)
    logger.info(
        "GANK (%s) killmail_id=%d system=%d region=%d victim_ship=%s by %s%s",
        source,
        event.killmail_id,
        event.solar_system_id,
        event.region_id,
        event.victim.ship_type_id,
        ", ".join(m.entity_name for m in matches) or "unlisted group",
        "" if matches else " (via zKillboard's ganked label)",
    )


def _process_sequence_update(
    conn, esi: ESIClient, r2z2: R2Z2Client, ganker_list: list[GankerListEntry], updated_sequence: int
) -> bool:
    """R2Z2 attaches `sequence_updated` to a later package when zKillboard
    retroactively edits an earlier one -- confirmed against zKillboard's
    own source (cron/9.ganked.php + cron/9.queueSequences.php) and its
    wiki ("API (R2Z2)"): this is exactly how "ganked" being added after
    the fact gets surfaced. Re-fetching that exact sequence gives us the
    corrected labels precisely when they change, no delay-guessing
    needed. Returns True if it turned out to be a gank."""
    updated_package = r2z2.fetch(updated_sequence)
    if updated_package is None:
        return False
    updated_event = parse_package(updated_package)
    matches = classify_gank(updated_event, ganker_list)
    if matches is None:
        return False
    _save_gank(conn, esi, updated_event, matches, source="sequence_updated")
    return True


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    db_path = Path(os.environ.get("GANK_DB_PATH", "gank_alert.sqlite3"))
    ganker_list_path = Path(
        os.environ.get(
            "GANK_GANKER_LIST_PATH",
            Path(__file__).parents[4] / "packages" / "shared" / "ganker_list.seed.json",
        )
    )

    ganker_list = load_ganker_list(ganker_list_path)
    logger.info(
        "watching all regions with %d ganker-list entries: %s",
        len(ganker_list),
        ", ".join(e.entity_name for e in ganker_list),
    )

    conn = storage.connect(db_path)
    esi = ESIClient(component="ingester")
    r2z2 = R2Z2Client()
    recheck_queue = RecheckQueue()

    start = storage.get_cursor(conn)
    if start is None:
        start = r2z2.latest_sequence()
        logger.info("no saved cursor, starting live from sequence %d", start)
    else:
        logger.info("resuming from saved cursor at sequence %d", start)

    processed = 0
    matched = 0
    try:
        for package in r2z2.iter_from(start):
            event = parse_package(package)

            matches = classify_gank(event, ganker_list)
            if matches is not None:
                _save_gank(conn, esi, event, matches, source="live")
                matched += 1
            elif needs_gank_recheck(event):
                recheck_queue.add(event)

            updated_sequence = package.get("sequence_updated")
            if updated_sequence and _process_sequence_update(
                conn, esi, r2z2, ganker_list, updated_sequence
            ):
                matched += 1

            for i, (pending, attempt) in enumerate(recheck_queue.pop_due()):
                if i > 0:
                    time.sleep(RECHECK_CALL_INTERVAL_SECONDS)
                pending.labels = fetch_current_labels(pending.killmail_id)
                recheck_matches = classify_gank(pending, ganker_list)
                if recheck_matches is not None:
                    _save_gank(conn, esi, pending, recheck_matches, source="recheck fallback")
                    matched += 1
                else:
                    recheck_queue.reschedule(pending, attempt)

            processed += 1
            if processed % 50 == 0:
                logger.info(
                    "heartbeat: processed=%d matched=%d cursor=%d pending_recheck=%d",
                    processed,
                    matched,
                    event.sequence_id,
                    len(recheck_queue),
                )
            storage.set_cursor(conn, event.sequence_id)
    except KeyboardInterrupt:
        logger.info("stopping (processed=%d, matched=%d)", processed, matched)
    finally:
        esi.close()
        r2z2.close()
        conn.close()


if __name__ == "__main__":
    run()
