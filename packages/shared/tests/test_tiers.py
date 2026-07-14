from gank_shared.tiers import tier_for_age


def test_fresh_under_one_hour():
    label, _ = tier_for_age(5)
    assert label == "FRESH"


def test_recent_between_one_and_two_hours():
    label, _ = tier_for_age(90)
    assert label == "RECENT"


def test_stay_wary_between_two_and_four_hours():
    label, _ = tier_for_age(180)
    assert label == "STAY WARY"


def test_none_past_four_hours():
    assert tier_for_age(241) is None


def test_returns_hex_color():
    _, color = tier_for_age(5)
    assert color.startswith("#")
    assert len(color) == 7
