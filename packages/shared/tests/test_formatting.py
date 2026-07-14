from gank_shared.formatting import format_isk


def test_format_isk_billions():
    assert format_isk(2_500_000_000) == "2.50B ISK"


def test_format_isk_millions():
    assert format_isk(15_000_000) == "15.0M ISK"


def test_format_isk_small():
    assert format_isk(1234) == "1,234 ISK"


def test_format_isk_none_or_zero():
    assert format_isk(None) == "unknown"
    assert format_isk(0) == "unknown"
