from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
-- Mirrors gank_ingester.storage's schema for gank_events -- the bot reads
-- this table but shouldn't hard-depend on the ingester having started
-- first to create it.
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

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    region_name TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_posts (
    guild_id INTEGER NOT NULL,
    killmail_id INTEGER NOT NULL,
    posted_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, killmail_id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def set_guild_region(conn: sqlite3.Connection, *, guild_id: int, channel_id: int, region_id: int, region_name: str) -> None:
    from datetime import UTC, datetime

    conn.execute(
        "INSERT INTO guild_settings (guild_id, channel_id, region_id, region_name, updated_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, "
        "region_id = excluded.region_id, region_name = excluded.region_name, updated_at = excluded.updated_at",
        (guild_id, channel_id, region_id, region_name, datetime.now(UTC).isoformat()),
    )
    conn.commit()


def all_guild_settings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM guild_settings").fetchall()


def unposted_events_for_guild(conn: sqlite3.Connection, *, guild_id: int, region_id: int, since_iso: str) -> list[tuple[int, str]]:
    return conn.execute(
        "SELECT killmail_id, payload_json FROM gank_events "
        "WHERE region_id = ? AND occurred_at >= ? "
        "AND killmail_id NOT IN (SELECT killmail_id FROM discord_posts WHERE guild_id = ?) "
        "ORDER BY occurred_at ASC",
        (region_id, since_iso, guild_id),
    ).fetchall()


def mark_posted(conn: sqlite3.Connection, *, guild_id: int, killmail_id: int) -> None:
    from datetime import UTC, datetime

    conn.execute(
        "INSERT OR IGNORE INTO discord_posts (guild_id, killmail_id, posted_at) VALUES (?, ?, ?)",
        (guild_id, killmail_id, datetime.now(UTC).isoformat()),
    )
    conn.commit()
