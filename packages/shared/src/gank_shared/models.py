from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class EntityType(StrEnum):
    CORPORATION = "corporation"
    ALLIANCE = "alliance"


class GankerListEntry(BaseModel):
    """One entry in the maintained list of known ganker corps/alliances."""

    entity_type: EntityType
    entity_id: int
    entity_name: str
    note: str = ""


class Participant(BaseModel):
    character_id: int | None = None
    corporation_id: int | None = None
    alliance_id: int | None = None
    faction_id: int | None = None
    ship_type_id: int | None = None
    damage: int = 0
    final_blow: bool = False


class GankEvent(BaseModel):
    """A killmail, resolved and classified against the ganker list."""

    killmail_id: int
    killmail_hash: str
    occurred_at: datetime
    solar_system_id: int
    region_id: int | None = None
    location_id: int | None = None
    """zkb.locationID -- a station/structure/celestial (belt, gate, moon,
    planet) ID pinpointing where in the system this happened. Resolve via
    ESIClient.resolve_location_name()."""

    victim: Participant
    attackers: list[Participant]

    total_value: float | None = None
    is_gank: bool = False
    matched_entities: list[GankerListEntry] = []

    sequence_id: int
    """R2Z2 sequence this was ingested at, used as the resume cursor."""
