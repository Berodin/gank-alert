from __future__ import annotations

from datetime import UTC, datetime

import discord

from gank_shared.formatting import format_isk
from gank_shared.tiers import tier_for_age


def collect_ids(event: dict) -> set[int]:
    ids = {event["solar_system_id"], event["victim"]["ship_type_id"]}
    for key in ("character_id", "corporation_id"):
        if event["victim"].get(key):
            ids.add(event["victim"][key])
    for attacker in event["attackers"]:
        if attacker.get("final_blow"):
            for key in ("character_id", "corporation_id", "alliance_id"):
                if attacker.get(key):
                    ids.add(attacker[key])
    return ids


def build_embed(event: dict, names: dict[int, str], location_name: str | None = None) -> discord.Embed | None:
    occurred_at = datetime.fromisoformat(event["occurred_at"])
    age_minutes = (datetime.now(UTC) - occurred_at).total_seconds() / 60

    tier = tier_for_age(age_minutes)
    if tier is None:
        return None
    label, hex_color = tier
    color = discord.Color(int(hex_color.lstrip("#"), 16))

    victim = event["victim"]
    ship_name = names.get(victim["ship_type_id"], f"ship type {victim['ship_type_id']}")
    system_name = names.get(event["solar_system_id"], f"system {event['solar_system_id']}")
    victim_name = names.get(victim.get("character_id"), "unknown pilot")
    victim_corp = names.get(victim.get("corporation_id"), "unknown corp")

    final_blow = next((a for a in event["attackers"] if a.get("final_blow")), None)
    if final_blow:
        attacker_name = names.get(final_blow.get("character_id"), "unknown")
        attacker_corp = names.get(final_blow.get("corporation_id"), "unknown corp")
        final_blow_str = f"{attacker_name} ({attacker_corp})"
    else:
        final_blow_str = "unknown"

    if event["matched_entities"]:
        ganker_tags = ", ".join(m["entity_name"] for m in event["matched_entities"])
    elif final_blow:
        # Not on our curated list, but zKillboard's own heuristic flagged
        # this as a gank -- we still know exactly who did it from the
        # killmail itself, so show that instead of a bare "unknown".
        ganker_tags = (
            names.get(final_blow.get("alliance_id"))
            or names.get(final_blow.get("corporation_id"))
            or "unknown"
        )
    else:
        ganker_tags = "unknown"

    embed = discord.Embed(
        title=f"[{label}] {ship_name} destroyed in {system_name}",
        url=f"https://zkillboard.com/kill/{event['killmail_id']}/",
        color=color,
        timestamp=occurred_at,
    )
    embed.set_thumbnail(url=f"https://images.evetech.net/types/{victim['ship_type_id']}/render?size=128")
    embed.add_field(name="Victim", value=f"{victim_name} ({victim_corp})", inline=False)
    embed.add_field(name="Final blow", value=final_blow_str, inline=True)
    embed.add_field(name="Ganker group", value=ganker_tags, inline=True)
    embed.add_field(name="Involved", value=str(len(event["attackers"])), inline=True)
    embed.add_field(name="Value", value=format_isk(event.get("total_value")), inline=True)
    if location_name:
        embed.add_field(name="Location", value=location_name, inline=True)
    embed.set_footer(text=f"{system_name}")
    return embed
