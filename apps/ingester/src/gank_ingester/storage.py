from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from gank_shared.models import GankEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gank_events (
    killmail_id INTEGER PRIMARY KEY,
    sequence_id INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    solar_system_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    posted_discord INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_gank_events_region_time
    ON gank_events (region_id, occurred_at DESC);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def get_cursor(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM state WHERE key = 'sequence_cursor'").fetchone()
    return int(row[0]) if row else None


def set_cursor(conn: sqlite3.Connection, sequence_id: int) -> None:
    conn.execute(
        "INSERT INTO state (key, value) VALUES ('sequence_cursor', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(sequence_id),),
    )
    conn.commit()


def save_gank_event(conn: sqlite3.Connection, event: GankEvent) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO gank_events "
        "(killmail_id, sequence_id, occurred_at, solar_system_id, region_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            event.killmail_id,
            event.sequence_id,
            event.occurred_at.isoformat(),
            event.solar_system_id,
            event.region_id,
            event.model_dump_json(),
        ),
    )
    conn.commit()
