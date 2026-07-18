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
    reminder_mode TEXT NOT NULL DEFAULT 'fresh_recent',
    updated_at TEXT NOT NULL
);

-- One row per (guild, killmail, tier) -- a kill is deliberately re-posted
-- as a reminder each time it crosses into a new staleness tier, not just
-- once. Which tiers actually trigger a reminder is per-guild (see
-- gank_bot.main.REMINDER_MODE_TIERS) -- STAY WARY never does, regardless
-- of mode. The tier is part of the key so each reminder fires exactly once.
CREATE TABLE IF NOT EXISTS discord_posts (
    guild_id INTEGER NOT NULL,
    killmail_id INTEGER NOT NULL,
    tier TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    PRIMARY KEY (guild_id, killmail_id, tier)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """CREATE TABLE IF NOT EXISTS in SCHEMA only helps on a fresh DB --
    existing production tables need columns added after the fact."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(guild_settings)")}
    if "reminder_mode" not in columns:
        conn.execute(
            "ALTER TABLE guild_settings ADD COLUMN reminder_mode TEXT NOT NULL DEFAULT 'fresh_recent'"
        )
        conn.commit()


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


def set_guild_reminder_mode(conn: sqlite3.Connection, *, guild_id: int, reminder_mode: str) -> bool:
    """Returns False if this guild has no settings row yet (region not set
    via /setregion), since guild_settings has no row to update in that case."""
    cur = conn.execute(
        "UPDATE guild_settings SET reminder_mode = ? WHERE guild_id = ?", (reminder_mode, guild_id)
    )
    conn.commit()
    return cur.rowcount > 0


def events_in_window_for_guild(conn: sqlite3.Connection, *, guild_id: int, region_id: int, since_iso: str) -> list[tuple[int, str]]:
    """All events still within the alert window (<4h old), regardless of
    whether they've already been posted -- tier-level dedup happens in the
    caller, since which tiers are already posted varies per killmail."""
    return conn.execute(
        "SELECT killmail_id, payload_json FROM gank_events "
        "WHERE region_id = ? AND occurred_at >= ? "
        "ORDER BY occurred_at ASC",
        (region_id, since_iso),
    ).fetchall()


def posted_tiers_for_guild(conn: sqlite3.Connection, *, guild_id: int) -> set[tuple[int, str]]:
    """(killmail_id, tier) pairs already posted for this guild, so the
    caller can skip tiers already sent and only post newly-crossed ones."""
    rows = conn.execute(
        "SELECT killmail_id, tier FROM discord_posts WHERE guild_id = ?", (guild_id,)
    ).fetchall()
    return {(killmail_id, tier) for killmail_id, tier in rows}


def mark_posted(conn: sqlite3.Connection, *, guild_id: int, killmail_id: int, tier: str) -> None:
    from datetime import UTC, datetime

    conn.execute(
        "INSERT OR IGNORE INTO discord_posts (guild_id, killmail_id, tier, posted_at) VALUES (?, ?, ?, ?)",
        (guild_id, killmail_id, tier, datetime.now(UTC).isoformat()),
    )
    conn.commit()
