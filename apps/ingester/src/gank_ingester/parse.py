from __future__ import annotations

from datetime import datetime

from gank_shared.models import EntityType, GankEvent, Participant


def attacker_entity_keys(event: GankEvent) -> set[tuple[EntityType, int]]:
    """Corp/alliance IDs of the *attackers* only -- deliberately excludes
    the victim, since a ganker corp getting CONCORD'd shows up as a
    separate killmail where that corp is the victim, which is evidence
    CONCORD responded, not the gank itself."""
    return {
        (etype, eid)
        for a in event.attackers
        for etype, eid in [(EntityType.CORPORATION, a.corporation_id), (EntityType.ALLIANCE, a.alliance_id)]
        if eid is not None
    }


def parse_package(package: dict) -> GankEvent:
    """Map a raw R2Z2 package ({killmail_id, hash, esi, zkb, sequence_id, ...})
    into our GankEvent. region_id and is_gank/matched_entities are filled in
    later by the caller once the system->region lookup and ganker-list
    classification have run.
    """
    esi = package["esi"]
    zkb = package["zkb"]

    victim = Participant(
        character_id=esi["victim"].get("character_id"),
        corporation_id=esi["victim"].get("corporation_id"),
        alliance_id=esi["victim"].get("alliance_id"),
        ship_type_id=esi["victim"].get("ship_type_id"),
        damage=esi["victim"].get("damage_taken", 0),
    )

    attackers = [
        Participant(
            character_id=a.get("character_id"),
            corporation_id=a.get("corporation_id"),
            alliance_id=a.get("alliance_id"),
            faction_id=a.get("faction_id"),
            ship_type_id=a.get("ship_type_id"),
            damage=a.get("damage_done", 0),
            final_blow=a.get("final_blow", False),
        )
        for a in esi["attackers"]
    ]

    return GankEvent(
        killmail_id=package["killmail_id"],
        killmail_hash=package["hash"],
        occurred_at=datetime.fromisoformat(esi["killmail_time"].replace("Z", "+00:00")),
        solar_system_id=esi["solar_system_id"],
        region_id=None,
        victim=victim,
        attackers=attackers,
        total_value=zkb.get("totalValue"),
        sequence_id=package["sequence_id"],
    )
