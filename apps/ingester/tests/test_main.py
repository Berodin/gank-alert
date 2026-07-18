import copy
from pathlib import Path

from gank_shared.models import EntityType, GankerListEntry

from gank_ingester import storage
from gank_ingester.main import _process_sequence_update
from gank_ingester.parse import parse_package

# Same shape as test_parse.py's SAMPLE_PACKAGE -- kept separate since main.py
# tests are about the sequence_updated wiring, not parsing itself.
SAMPLE_PACKAGE = {
    "killmail_id": 137000243,
    "hash": "5838074782c67102caca15ba1c965796703aa77c",
    "esi": {
        "attackers": [
            {
                "alliance_id": 99003581,
                "character_id": 2122980578,
                "corporation_id": 98598862,
                "damage_done": 461,
                "final_blow": True,
                "security_status": -4.9,
                "ship_type_id": 17843,
                "weapon_type_id": 3138,
            }
        ],
        "killmail_id": 137000243,
        "killmail_time": "2026-07-14T06:52:09Z",
        "solar_system_id": 30001784,
        "victim": {
            "alliance_id": 99011990,
            "character_id": 2121403348,
            "corporation_id": 98746772,
            "damage_taken": 461,
            "items": [],
            "position": {"x": 1.0, "y": 2.0, "z": 3.0},
            "ship_type_id": 670,
        },
    },
    "zkb": {
        "locationID": 40114185,
        "hash": "5838074782c67102caca15ba1c965796703aa77c",
        "totalValue": 15_000_000,
        "points": 1,
        "npc": False,
        "solo": False,
        "awox": False,
        "labels": ["tz:usw", "loc:highsec"],
    },
    "uploaded_at": 1784012057,
    "sequence_id": 98531146,
}

LISTED_GANKER = GankerListEntry(
    entity_type=EntityType.ALLIANCE, entity_id=99003581, entity_name="Test Ganker Alliance"
)


class FakeESI:
    def region_id_for_system(self, solar_system_id: int) -> int:
        return 10000002


class FakeR2Z2:
    def __init__(self, packages: dict[int, dict | None]) -> None:
        self.packages = packages
        self.fetched: list[int] = []

    def fetch(self, sequence_id: int) -> dict | None:
        self.fetched.append(sequence_id)
        return self.packages.get(sequence_id)


def _conn():
    return storage.connect(Path(":memory:"))


def test_sequence_update_saves_now_ganked_kill():
    updated_package = copy.deepcopy(SAMPLE_PACKAGE)
    updated_package["zkb"]["labels"] = ["tz:usw", "loc:highsec", "ganked"]
    r2z2 = FakeR2Z2({98531146: updated_package})
    conn = _conn()

    result = _process_sequence_update(conn, FakeESI(), r2z2, [LISTED_GANKER], 98531146)

    assert result is True
    assert r2z2.fetched == [98531146]
    row = conn.execute("SELECT killmail_id FROM gank_events WHERE killmail_id = 137000243").fetchone()
    assert row is not None


def test_sequence_update_not_a_gank_saves_nothing():
    # Updated but still missing "ganked" -- e.g. some other metadata changed.
    r2z2 = FakeR2Z2({98531146: copy.deepcopy(SAMPLE_PACKAGE)})
    conn = _conn()

    result = _process_sequence_update(conn, FakeESI(), r2z2, [LISTED_GANKER], 98531146)

    assert result is False
    assert conn.execute("SELECT COUNT(*) FROM gank_events").fetchone()[0] == 0


def test_sequence_update_fetch_returns_none_is_handled():
    """The pointed-at sequence may already be gone (R2 retention) --
    should not raise, just report nothing found."""
    r2z2 = FakeR2Z2({})
    conn = _conn()

    result = _process_sequence_update(conn, FakeESI(), r2z2, [LISTED_GANKER], 98531146)

    assert result is False


def test_sample_package_is_a_valid_r2z2_shape():
    # Sanity check that our fixture parses the same way test_parse.py's does.
    event = parse_package(SAMPLE_PACKAGE)
    assert event.killmail_id == 137000243
