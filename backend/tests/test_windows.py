from datetime import date, datetime, timezone

import pytest

from windows import month_window, range_window


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_month_window_regular():
    assert month_window("2026-01") == (utc(2026, 1, 1), utc(2026, 2, 1))


def test_month_window_december_rolls_year():
    assert month_window("2025-12") == (utc(2025, 12, 1), utc(2026, 1, 1))


@pytest.mark.parametrize("bad", ["2026-13", "2026", "jan", "2026-1-1", ""])
def test_month_window_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        month_window(bad)


def test_range_window_end_inclusive():
    assert range_window(date(2026, 1, 5), date(2026, 1, 7)) == (utc(2026, 1, 5), utc(2026, 1, 8))


def test_range_window_single_day():
    assert range_window(date(2026, 1, 5), date(2026, 1, 5)) == (utc(2026, 1, 5), utc(2026, 1, 6))


def test_range_window_end_before_start():
    with pytest.raises(ValueError, match="before"):
        range_window(date(2026, 1, 7), date(2026, 1, 5))
