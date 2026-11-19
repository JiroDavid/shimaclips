import sqlite3
from datetime import date

import pytest

from ask.dates import resolve
from ask.tools import ToolError, count_clips, open_readonly, top_clips

TODAY = date(2026, 11, 19)


@pytest.mark.parametrize("phrase,expected", [
    ("today", (date(2026, 11, 19), date(2026, 11, 20))),
    ("yesterday", (date(2026, 11, 18), date(2026, 11, 19))),
    ("this week", (date(2026, 11, 16), date(2026, 11, 23))),
    ("last week", (date(2026, 11, 9), date(2026, 11, 16))),
    ("this month", (date(2026, 11, 1), date(2026, 12, 1))),
    ("last month", (date(2026, 10, 1), date(2026, 11, 1))),
    ("this year", (date(2026, 1, 1), date(2027, 1, 1))),
    ("2025", (date(2025, 1, 1), date(2026, 1, 1))),
    ("2026-12", (date(2026, 12, 1), date(2027, 1, 1))),
    ("March 2025", (date(2025, 3, 1), date(2025, 4, 1))),
    ("december", (date(2026, 12, 1), date(2027, 1, 1))),
    ("Feb 2026", (date(2026, 2, 1), date(2026, 3, 1))),
    ("all time", (date(2007, 1, 1), date(2026, 11, 20))),
    ("of all time", (date(2007, 1, 1), date(2026, 11, 20))),
    ("in 2024", (date(2024, 1, 1), date(2025, 1, 1))),
    ("during March 2025?", (date(2025, 3, 1), date(2025, 4, 1))),
    ("in the past 30 days", (date(2026, 10, 21), date(2026, 11, 20))),
    ("sept", (date(2026, 9, 1), date(2026, 10, 1))),
    ("mar", (date(2026, 3, 1), date(2026, 4, 1))),
])
def test_resolve(phrase, expected):
    assert resolve(phrase, TODAY) == expected


def test_resolve_last_month_across_year_boundary():
    assert resolve("last month", date(2026, 1, 5)) == (date(2025, 12, 1), date(2026, 1, 1))


def test_resolve_unknown_is_none():
    assert resolve("whenever", TODAY) is None


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "t.db"
    c = sqlite3.connect(path)
    c.executescript(
        "CREATE TABLE streamers (broadcaster_id TEXT PRIMARY KEY, login TEXT, display_name TEXT, account_created TEXT);"
        "CREATE TABLE clips (id TEXT PRIMARY KEY, broadcaster_id TEXT, url TEXT, title TEXT, thumbnail_url TEXT,"
        " view_count INTEGER, duration REAL, creator_name TEXT, created_at TEXT);"
    )
    c.execute("INSERT INTO streamers VALUES ('1', 'jay', 'Jay', '2020-01-01')")
    for i, (views, day) in enumerate([(10, "2026-11-02"), (500, "2026-11-10"), (50, "2026-11-30"), (999, "2026-12-01")]):
        c.execute(
            "INSERT INTO clips VALUES (?, '1', ?, ?, '', ?, 30, 'x', ?)",
            (f"c{i}", f"https://clips/{i}", f"t{i}", views, f"{day}T12:00:00Z"),
        )
    c.commit()
    c.close()
    return open_readonly(path)


def test_count_is_half_open(conn):
    assert count_clips(conn, "jay", "2026-11-01", "2026-12-01")["count"] == 3


def test_top_clips_sorted_and_limited(conn):
    r = top_clips(conn, "jay", "2026-11-01", "2026-12-01", limit=2)
    assert [c["id"] for c in r["clips"]] == ["c1", "c2"]


def test_limit_is_clamped(conn):
    assert len(top_clips(conn, "jay", "2026-01-01", "2027-01-01", limit=10_000)["clips"]) == 4


def test_unknown_streamer_and_bad_dates_rejected(conn):
    with pytest.raises(ToolError):
        count_clips(conn, "nobody", "2026-11-01", "2026-12-01")
    with pytest.raises(ToolError):
        count_clips(conn, "jay", "tomorrow", "2026-12-01")
    with pytest.raises(ToolError):
        count_clips(conn, "jay", "2026-12-01", "2026-11-01")


def test_connection_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM clips")


@pytest.mark.parametrize("phrase,expected", [
    ("the month before last", (date(2026, 9, 1), date(2026, 10, 1))),
    ("past 30 days", (date(2026, 10, 21), date(2026, 11, 20))),
    ("last 7 days", (date(2026, 11, 13), date(2026, 11, 20))),
    ("2026-11-10", (date(2026, 11, 10), date(2026, 11, 11))),
])
def test_resolve_rolling_and_exact(phrase, expected):
    assert resolve(phrase, TODAY) == expected


def test_resolve_month_before_last_across_year():
    assert resolve("month before last", date(2026, 1, 5)) == (date(2025, 11, 1), date(2025, 12, 1))


def test_resolve_rejects_impossible_date():
    assert resolve("2026-02-31", TODAY) is None


def test_since_is_not_silently_treated_as_a_single_month():
    assert resolve("since March", TODAY) is None
