from __future__ import annotations

from datetime import datetime

from gank_shared.ganker_list import classify
from gank_shared.models import EntityType, GankEvent, GankerListEntry, Participant


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


def classify_gank(event: GankEvent, ganker_list: list[GankerListEntry]) -> list[GankerListEntry] | None:
    """Decides whether `event` counts as a gank at all, and if so, which
    curated-list entries (if any) it matches.

    zKillboard's own "ganked" label (plus highsec, which it implies but we
    check explicitly anyway) is the *sole* authority on whether this is a
    gank -- a curated-list group doing perfectly normal highsec PvP
    (mission running, a duel, a wardec kill, whatever) is not a gank just
    because they're on the list. The list is only used for attribution:
    when zKillboard says "ganked" AND the attacker is a group we track,
    matched_entities names them; when it says "ganked" but the attacker
    isn't tracked, matched_entities comes back empty and callers should
    fall back to the killmail's own attacker corp/alliance instead of a
    bare "unknown".

    Returns None if this isn't a gank at all.
    """
    if "loc:highsec" not in event.labels or "ganked" not in event.labels:
        return None

    return classify(attacker_entity_keys(event), ganker_list)


def needs_gank_recheck(event: GankEvent) -> bool:
    """True if `event` is a highsec kill without "ganked" yet but could
    plausibly get it later -- worth queuing for a delayed fallback
    recheck (see gank_ingester.recheck). Confirmed against zKillboard's
    own source (cron/9.ganked.php): "ganked" is added by a batch job that
    correlates the victim's kill with CONCORD killing the attacker, and
    it unconditionally skips any kill with zkb.totalValue below 1,000,000
    ISK -- those can never get the label, so there's no point queuing
    them. NPC kills are excluded for the same reason: never a gank."""
    return (
        "loc:highsec" in event.labels
        and "ganked" not in event.labels
        and "npc" not in event.labels
        and (event.total_value is None or event.total_value >= 1_000_000)
    )


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
        location_id=zkb.get("locationID"),
        labels=zkb.get("labels", []),
        victim=victim,
        attackers=attackers,
        total_value=zkb.get("totalValue"),
        sequence_id=package["sequence_id"],
    )
