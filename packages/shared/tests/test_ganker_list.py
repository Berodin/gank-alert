from gank_shared.ganker_list import classify
from gank_shared.models import EntityType, GankerListEntry

CODE = GankerListEntry(entity_type=EntityType.ALLIANCE, entity_id=99002775, entity_name="CODE.")
SAFETY = GankerListEntry(entity_type=EntityType.ALLIANCE, entity_id=99010569, entity_name="Safety.")
GANKER_LIST = [CODE, SAFETY]


def test_classify_matches_attacker_alliance():
    attackers = {(EntityType.ALLIANCE, 99002775)}
    assert classify(attackers, GANKER_LIST) == [CODE]


def test_classify_matches_multiple_entries():
    attackers = {(EntityType.ALLIANCE, 99002775), (EntityType.ALLIANCE, 99010569)}
    assert classify(attackers, GANKER_LIST) == [CODE, SAFETY]


def test_classify_no_match_returns_empty():
    attackers = {(EntityType.CORPORATION, 12345), (EntityType.ALLIANCE, 999)}
    assert classify(attackers, GANKER_LIST) == []
