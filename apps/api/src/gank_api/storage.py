from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
-- Mirrors gank_ingester.storage's schema for gank_events -- api reads this
-- table (GET /feed) but shouldn't hard-depend on the ingester having
-- started first to create it.
CREATE TABLE IF NOT EXISTS gank_events (
    killmail_id INTEGER PRIMARY KEY,
    sequence_id INTEGER NOT NULL,
    occurred_at TEXT NOT NULL,
    solar_system_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gank_events_region_time
    ON gank_events (region_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS api_tokens (
    token_hash TEXT PRIMARY KEY,
    character_id INTEGER NOT NULL,
    character_name TEXT NOT NULL,
    eve_access_token TEXT NOT NULL,
    eve_refresh_token TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS character_locations (
    character_id INTEGER PRIMARY KEY,
    solar_system_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn
