import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gank_bot import storage


def _insert_gank_event(conn, *, killmail_id: int, region_id: int, minutes_ago: float) -> None:
    occurred_at = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    conn.execute(
        "INSERT INTO gank_events (killmail_id, sequence_id, occurred_at, solar_system_id, region_id, payload_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (killmail_id, killmail_id, occurred_at, 30000142, region_id, json.dumps({"killmail_id": killmail_id})),
    )
    conn.commit()


def test_set_guild_region_then_read_back(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000002, region_name="The Forge")

    rows = storage.all_guild_settings(conn)
    assert len(rows) == 1
    assert rows[0]["guild_id"] == 1
    assert rows[0]["channel_id"] == 2
    assert rows[0]["region_id"] == 10000002
    assert rows[0]["region_name"] == "The Forge"


def test_set_guild_region_upserts_on_same_guild(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000002, region_name="The Forge")
    storage.set_guild_region(conn, guild_id=1, channel_id=3, region_id=10000043, region_name="Domain")

    rows = storage.all_guild_settings(conn)
    assert len(rows) == 1
    assert rows[0]["channel_id"] == 3
    assert rows[0]["region_name"] == "Domain"


def test_unposted_events_filters_by_region(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    _insert_gank_event(conn, killmail_id=2, region_id=10000043, minutes_ago=5)

    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    rows = storage.unposted_events_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)

    assert [r[0] for r in rows] == [1]


def test_unposted_events_filters_by_age(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    _insert_gank_event(conn, killmail_id=2, region_id=10000002, minutes_ago=300)

    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    rows = storage.unposted_events_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)

    assert [r[0] for r in rows] == [1]


def test_mark_posted_excludes_from_future_queries(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()

    assert len(storage.unposted_events_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)) == 1
    storage.mark_posted(conn, guild_id=1, killmail_id=1)
    assert len(storage.unposted_events_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)) == 0


def test_mark_posted_is_per_guild_not_global(tmp_path: Path):
    """The same kill can be relevant to two guilds watching the same
    region -- posting it for guild A must not hide it from guild B."""
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()

    storage.mark_posted(conn, guild_id=1, killmail_id=1)

    still_pending_for_other_guild = storage.unposted_events_for_guild(
        conn, guild_id=2, region_id=10000002, since_iso=since
    )
    assert len(still_pending_for_other_guild) == 1
