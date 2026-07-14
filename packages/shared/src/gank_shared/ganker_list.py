from __future__ import annotations

import json
from pathlib import Path

from gank_shared.models import EntityType, GankerListEntry


def load_ganker_list(path: Path) -> list[GankerListEntry]:
    data = json.loads(path.read_text())
    return [GankerListEntry(**entry) for entry in data]


def classify(
    attackers_entity_ids: set[tuple[EntityType, int]],
    ganker_list: list[GankerListEntry],
) -> list[GankerListEntry]:
    """Match a killmail's attacker corps/alliances against the ganker list.

    We match on attackers, not the victim: a ganker corp getting CONCORD'd
    shows up as a *separate* killmail where that corp is the victim -- that's
    evidence CONCORD responded, not the gank itself.
    """
    return [
        entry
        for entry in ganker_list
        if (entry.entity_type, entry.entity_id) in attackers_entity_ids
    ]
