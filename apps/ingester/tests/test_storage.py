from datetime import UTC, datetime
from pathlib import Path

from gank_shared.models import GankEvent, GankerListEntry, EntityType, Participant

from gank_ingester import storage


def _event(killmail_id: int = 1, sequence_id: int = 1) -> GankEvent:
    return GankEvent(
        killmail_id=killmail_id,
        killmail_hash="x",
        occurred_at=datetime.now(UTC),
        solar_system_id=30000142,
        region_id=10000002,
        victim=Participant(ship_type_id=649),
        attackers=[Participant(corporation_id=1, final_blow=True)],
        is_gank=True,
        matched_entities=[GankerListEntry(entity_type=EntityType.ALLIANCE, entity_id=1, entity_name="X")],
        sequence_id=sequence_id,
    )


def test_cursor_defaults_to_none(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    assert storage.get_cursor(conn) is None


def test_cursor_round_trips(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_cursor(conn, 42)
    assert storage.get_cursor(conn) == 42


def test_cursor_update_overwrites(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.set_cursor(conn, 1)
    storage.set_cursor(conn, 2)
    assert storage.get_cursor(conn) == 2


def test_save_and_query_gank_event(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.save_gank_event(conn, _event(killmail_id=100))

    row = conn.execute("SELECT killmail_id, region_id FROM gank_events").fetchone()
    assert row == (100, 10000002)


def test_save_gank_event_is_idempotent_on_killmail_id(tmp_path: Path):
    conn = storage.connect(tmp_path / "db.sqlite3")
    storage.save_gank_event(conn, _event(killmail_id=100, sequence_id=1))
    storage.save_gank_event(conn, _event(killmail_id=100, sequence_id=2))

    count = conn.execute("SELECT COUNT(*) FROM gank_events").fetchone()[0]
    assert count == 1
