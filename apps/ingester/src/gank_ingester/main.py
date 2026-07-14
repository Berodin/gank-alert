from __future__ import annotations

import logging
import os
from pathlib import Path

from gank_shared.esi import ESIClient
from gank_shared.ganker_list import classify, load_ganker_list

from gank_ingester import storage
from gank_ingester.parse import attacker_entity_keys, parse_package
from gank_ingester.r2z2 import R2Z2Client

logger = logging.getLogger("gank_ingester")


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

            # Classify first (cheap, in-memory) -- only pay for the ESI
            # region lookup on kills that actually matter. Region isn't a
            # discovery filter anymore: the ingester watches the whole
            # galaxy for the ganker list, and each Discord guild picks
            # which region's matches it wants alerts for.
            matches = classify(attacker_entity_keys(event), ganker_list)
            if matches:
                event.region_id = esi.region_id_for_system(event.solar_system_id)
                event.is_gank = True
                event.matched_entities = matches
                storage.save_gank_event(conn, event)
                matched += 1
                logger.info(
                    "GANK killmail_id=%d system=%d region=%d victim_ship=%s by %s",
                    event.killmail_id,
                    event.solar_system_id,
                    event.region_id,
                    event.victim.ship_type_id,
                    ", ".join(m.entity_name for m in matches),
                )

            processed += 1
            if processed % 50 == 0:
                logger.info(
                    "heartbeat: processed=%d matched=%d cursor=%d", processed, matched, event.sequence_id
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
