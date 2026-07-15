from datetime import UTC, datetime, timedelta

from gank_shared.tiers import tier_for_age

from gank_bot.embeds import build_embed, collect_ids


def _event(minutes_ago: float, total_value: float | None = 15_000_000.0) -> dict:
    occurred_at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    return {
        "killmail_id": 1,
        "occurred_at": occurred_at.isoformat(),
        "solar_system_id": 30002187,
        "victim": {"character_id": 10, "corporation_id": 20, "ship_type_id": 649, "damage": 100},
        "attackers": [
            {"character_id": 30, "corporation_id": 40, "alliance_id": 50, "final_blow": True, "damage": 100}
        ],
        "total_value": total_value,
        "matched_entities": [{"entity_type": "alliance", "entity_id": 50, "entity_name": "CODE."}],
    }


def test_tier_for_age_fresh():
    label, _ = tier_for_age(5)
    assert label == "FRESH"


def test_tier_for_age_recent():
    label, _ = tier_for_age(90)
    assert label == "RECENT"


def test_tier_for_age_stay_wary():
    label, _ = tier_for_age(180)
    assert label == "STAY WARY"


def test_tier_for_age_too_old_is_none():
    assert tier_for_age(241) is None


def test_collect_ids_includes_victim_and_final_blow_attacker_only():
    event = _event(minutes_ago=1)
    ids = collect_ids(event)

    assert 30002187 in ids  # system
    assert 649 in ids  # ship type
    assert 10 in ids and 20 in ids  # victim char + corp
    assert 30 in ids and 40 in ids  # final-blow attacker char + corp


def test_collect_ids_ignores_non_final_blow_attackers():
    event = _event(minutes_ago=1)
    event["attackers"].append(
        {"character_id": 999, "corporation_id": 888, "final_blow": False, "damage": 1}
    )
    ids = collect_ids(event)

    assert 999 not in ids
    assert 888 not in ids


def test_build_embed_none_for_stale_kill():
    event = _event(minutes_ago=300)
    assert build_embed(event, names={}) is None


def test_build_embed_uses_resolved_names():
    event = _event(minutes_ago=5)
    names = {
        30002187: "Amarr",
        649: "Tayra",
        10: "Some Victim",
        20: "Victim Corp",
        30: "Some Attacker",
        40: "Attacker Corp",
    }

    embed = build_embed(event, names)

    assert embed is not None
    assert "FRESH" in embed.title
    assert "Tayra" in embed.title
    assert "Amarr" in embed.title
    field_values = {f.name: f.value for f in embed.fields}
    assert field_values["Victim"] == "Some Victim (Victim Corp)"
    assert field_values["Final blow"] == "Some Attacker (Attacker Corp)"
    assert field_values["Ganker group"] == "CODE."
    assert "15.0M" in field_values["Value"]


def test_build_embed_falls_back_to_raw_ids_when_unresolved():
    event = _event(minutes_ago=5)
    embed = build_embed(event, names={})

    assert "ship type 649" in embed.title
    assert "system 30002187" in embed.title


def test_build_embed_includes_location_when_given():
    event = _event(minutes_ago=5)
    embed = build_embed(event, names={}, location_name="Simela VII - Asteroid Belt 2")

    field_values = {f.name: f.value for f in embed.fields}
    assert field_values["Location"] == "Simela VII - Asteroid Belt 2"


def test_build_embed_omits_location_field_when_not_given():
    event = _event(minutes_ago=5)
    embed = build_embed(event, names={})

    field_names = {f.name for f in embed.fields}
    assert "Location" not in field_names
