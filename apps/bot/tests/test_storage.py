import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gank_shared.tiers import tier_for_age

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


def test_set_guild_region_defaults_reminder_mode_to_fresh_recent(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000002, region_name="The Forge")

    rows = storage.all_guild_settings(conn)
    assert rows[0]["reminder_mode"] == "fresh_recent"


def test_set_guild_reminder_mode_updates_existing_row(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000002, region_name="The Forge")

    updated = storage.set_guild_reminder_mode(conn, guild_id=1, reminder_mode="fresh_only")

    assert updated is True
    rows = storage.all_guild_settings(conn)
    assert rows[0]["reminder_mode"] == "fresh_only"


def test_set_guild_reminder_mode_without_a_region_set_first_returns_false(tmp_path: Path):
    """No guild_settings row exists yet -- /setreminders before /setregion
    has nothing to update."""
    conn = storage.connect(tmp_path / "db.sqlite3")

    updated = storage.set_guild_reminder_mode(conn, guild_id=1, reminder_mode="fresh_only")

    assert updated is False


def test_set_guild_region_upsert_preserves_reminder_mode(tmp_path: Path):
    """Re-running /setregion (e.g. to change region) must not silently
    reset a reminder mode the guild already configured."""
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000002, region_name="The Forge")
    storage.set_guild_reminder_mode(conn, guild_id=1, reminder_mode="fresh_only")

    storage.set_guild_region(conn, guild_id=1, channel_id=2, region_id=10000043, region_name="Domain")

    rows = storage.all_guild_settings(conn)
    assert rows[0]["reminder_mode"] == "fresh_only"


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
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="FRESH")

    posted = storage.posted_tiers_for_guild(conn, guild_id=1)
    assert posted == {(100, "FRESH")}

    # posting a later tier for the same kill is a separate reminder, not a dup
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="RECENT")
    posted = storage.posted_tiers_for_guild(conn, guild_id=1)
    assert posted == {(100, "FRESH"), (100, "RECENT")}


def test_mark_posted_same_tier_twice_is_idempotent(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="FRESH")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="FRESH")

    count = conn.execute("SELECT COUNT(*) FROM discord_posts").fetchone()[0]
    assert count == 1


def test_posted_tiers_is_per_guild_not_global(tmp_path: Path):
    """The same kill can be relevant to two guilds watching the same
    region -- posting it for guild A must not hide it from guild B."""
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier="FRESH")

    assert storage.posted_tiers_for_guild(conn, guild_id=1) == {(100, "FRESH")}
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
    into RECENT, even though it was already posted as FRESH."""
    conn = storage.connect(tmp_path / "db.sqlite3")

    due = _tier_dedup(conn, guild_id=1, killmail_id=100, age_minutes=5)
    assert due == "FRESH"
    storage.mark_posted(conn, guild_id=1, killmail_id=100, tier=due)

    # still within FRESH, already posted -- not due again yet
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
