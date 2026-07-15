from gank_shared.models import EntityType

from gank_ingester.parse import attacker_entity_keys, parse_package

# Shape verified live against https://r2z2.zkillboard.com/ephemeral/<n>.json
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
        "totalValue": 10000,
        "points": 1,
        "npc": False,
        "solo": False,
        "awox": False,
        "labels": ["tz:usw", "pvp", "loc:nullsec"],
    },
    "uploaded_at": 1784012057,
    "sequence_id": 98531146,
}


def test_parse_package_maps_core_fields():
    event = parse_package(SAMPLE_PACKAGE)

    assert event.killmail_id == 137000243
    assert event.killmail_hash == "5838074782c67102caca15ba1c965796703aa77c"
    assert event.solar_system_id == 30001784
    assert event.sequence_id == 98531146
    assert event.total_value == 10000
    assert event.location_id == 40114185
    assert event.region_id is None  # filled in later by the caller
    assert event.is_gank is False


def test_parse_package_maps_victim_and_attackers():
    event = parse_package(SAMPLE_PACKAGE)

    assert event.victim.character_id == 2121403348
    assert event.victim.ship_type_id == 670

    assert len(event.attackers) == 1
    attacker = event.attackers[0]
    assert attacker.corporation_id == 98598862
    assert attacker.alliance_id == 99003581
    assert attacker.final_blow is True


def test_parse_package_handles_missing_optional_fields():
    package = {
        "killmail_id": 1,
        "hash": "x",
        "esi": {
            "killmail_time": "2026-01-01T00:00:00Z",
            "solar_system_id": 1,
            "victim": {"ship_type_id": 1, "damage_taken": 0},
            "attackers": [{"damage_done": 0, "final_blow": True}],
        },
        "zkb": {},
        "sequence_id": 1,
    }

    event = parse_package(package)

    assert event.victim.character_id is None
    assert event.attackers[0].corporation_id is None
    assert event.total_value is None


def test_attacker_entity_keys_excludes_victim():
    event = parse_package(SAMPLE_PACKAGE)
    keys = attacker_entity_keys(event)

    assert (EntityType.ALLIANCE, 99003581) in keys
    assert (EntityType.CORPORATION, 98598862) in keys
    # victim's alliance/corp must never appear -- getting CONCORD'd is a
    # separate killmail, not evidence this one is a gank.
    assert (EntityType.ALLIANCE, 99011990) not in keys
    assert (EntityType.CORPORATION, 98746772) not in keys


def test_attacker_entity_keys_skips_none_ids():
    package = {
        "killmail_id": 1,
        "hash": "x",
        "esi": {
            "killmail_time": "2026-01-01T00:00:00Z",
            "solar_system_id": 1,
            "victim": {"ship_type_id": 1, "damage_taken": 0},
            "attackers": [{"damage_done": 0, "final_blow": True}],  # NPC, no corp/alliance
        },
        "zkb": {},
        "sequence_id": 1,
    }
    event = parse_package(package)

    assert attacker_entity_keys(event) == set()
