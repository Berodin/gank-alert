from gank_bot.main import DEFAULT_REMINDER_MODE, _tier_allowed


def test_fresh_only_allows_fresh_but_not_recent_or_stay_wary():
    assert _tier_allowed("fresh_only", "FRESH") is True
    assert _tier_allowed("fresh_only", "RECENT") is False
    assert _tier_allowed("fresh_only", "STAY WARY") is False


def test_fresh_recent_allows_fresh_and_recent_but_never_stay_wary():
    assert _tier_allowed("fresh_recent", "FRESH") is True
    assert _tier_allowed("fresh_recent", "RECENT") is True
    assert _tier_allowed("fresh_recent", "STAY WARY") is False


def test_unknown_mode_falls_back_to_default():
    assert _tier_allowed("some-old-value", "FRESH") is _tier_allowed(DEFAULT_REMINDER_MODE, "FRESH")
    assert _tier_allowed("some-old-value", "RECENT") is _tier_allowed(DEFAULT_REMINDER_MODE, "RECENT")
