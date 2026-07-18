from gank_bot.main import DEFAULT_REMINDER_MODE, _reminder_allowed


def test_fresh_only_allows_exactly_one_post():
    assert _reminder_allowed("fresh_only", already_posted_count=0) is True
    assert _reminder_allowed("fresh_only", already_posted_count=1) is False


def test_fresh_recent_allows_up_to_two_posts():
    assert _reminder_allowed("fresh_recent", already_posted_count=0) is True
    assert _reminder_allowed("fresh_recent", already_posted_count=1) is True
    assert _reminder_allowed("fresh_recent", already_posted_count=2) is False


def test_fresh_only_still_allows_the_first_post_even_if_already_stale():
    """zKillboard's "ganked" labeling is retroactive and sometimes slow --
    a kill's first-ever sighting can already be past the FRESH tier (a
    real production case took 67 minutes). fresh_only must still grant
    that first post: the cap is on *count*, not on which literal tier
    this happens to be -- the alternative is total silence for a real
    gank, which defeats the point of the mode."""
    assert _reminder_allowed("fresh_only", already_posted_count=0) is True


def test_unknown_mode_falls_back_to_default():
    for count in (0, 1, 2):
        assert _reminder_allowed("some-old-value", count) is _reminder_allowed(DEFAULT_REMINDER_MODE, count)
