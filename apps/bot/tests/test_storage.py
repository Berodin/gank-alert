import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gank_bot import storage
from gank_bot.embeds import tier_for_age


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


def test_events_in_window_filters_by_region(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    _insert_gank_event(conn, killmail_id=2, region_id=10000043, minutes_ago=5)

    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    rows = storage.events_in_window_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)

    assert [r[0] for r in rows] == [1]


def test_events_in_window_filters_by_age(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    _insert_gank_event(conn, killmail_id=1, region_id=10000002, minutes_ago=5)
    _insert_gank_event(conn, killmail_id=2, region_id=10000002, minutes_ago=300)

    since = (datetime.now(UTC) - timedelta(hours=4)).isoformat()
    rows = storage.events_in_window_for_guild(conn, guild_id=1, region_id=10000002, since_iso=since)

    assert [r[0] for r in rows] == [1]


def test_mark_posted_is_per_tier(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="IMMINENT")

    posted = storage.posted_tiers_for_guild(conn, guild_id=1)
    assert posted == {(100, "IMMINENT")}

    # posting a later tier for the same kill is a separate reminder, not a dup
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="RECENT")
    posted = storage.posted_tiers_for_guild(conn, guild_id=1)
    assert posted == {(100, "IMMINENT"), (100, "RECENT")}


def test_mark_posted_same_tier_twice_is_idempotent(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="IMMINENT")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="IMMINENT")

    count = conn.execute("SELECT COUNT(*) FROM discord_posts").fetchone()[0]
    assert count == 1


def test_posted_tiers_is_per_guild_not_global(tmp_path: Path):
    """The same kill can be relevant to two guilds watching the same
    region -- posting it for guild A must not hide it from guild B."""
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="IMMINENT")

    assert storage.posted_tiers_for_guild(conn, guild_id=1) == {(100, "IMMINENT")}
    assert storage.posted_tiers_for_guild(conn, guild_id=2) == set()


def _tier_dedup(conn, *, guild_id: int, killmail_id: int, age_minutes: float) -> str | None:
    """Mirrors the dedup check in gank_bot.main._post_for_guild: given a
    kill's current age, is there a not-yet-posted tier for it?"""
    tier = tier_for_age(age_minutes)
    if tier is None:
        return None
    label, _ = tier
    if (killmail_id, label) in storage.posted_tiers_for_guild(conn, guild_id=guild_id):
        return None
    return label


def test_same_kill_is_due_again_after_crossing_into_a_new_tier(tmp_path: Path):
    """This is the actual point of the tiering system: a reminder, not a
    one-shot notice. The same killmail must come due again once it ages
    into RECENT, even though it was already posted as IMMINENT."""
    conn = storage.connect(tmp_path / "db.sqlite3")

    due = _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=5)
    assert due == "IMMINENT"
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier=due)

    # still within IMMINENT, already posted -- not due again yet
    assert _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=50) is None

    # aged into RECENT -- due as a reminder
    due = _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=90)
    assert due == "RECENT"
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier=due)

    # aged into STAY WARY -- due again
    due = _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=200)
    assert due == "STAY WARY"
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier=due)

    # past 4h -- never due again
    assert _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=300) is None
