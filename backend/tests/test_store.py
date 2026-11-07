from datetime import date, datetime, timedelta, timezone

from store import SCHEMA_VERSION, SEED_WATCHLIST, Store, WatchEntry
from twitch import Clip, User

UTC = timezone.utc


def dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def clip(cid, created, views=1):
    return Clip(
        id=cid,
        url=f"https://clips.twitch.tv/{cid}",
        title=cid,
        thumbnail_url="https://example/t.jpg",
        view_count=views,
        duration=10.0,
        creator_name="c",
        created_at=created,
    )


def make(tmp_path):
    return Store(tmp_path / "s.db")


def test_streamer_roundtrip(tmp_path):
    s = make(tmp_path)
    assert s.get_streamer("shima") is None
    s.upsert_streamer(User("1", "shima", "Shima", dt(2020, 1, 2)))
    st = s.get_streamer("shima")
    assert st.broadcaster_id == "1"
    assert st.account_created == dt(2020, 1, 2)


def test_upsert_clips_dedupes_by_id(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [clip("a", "2026-01-01T00:00:00Z", 1)])
    s.upsert_clips("1", [clip("a", "2026-01-01T00:00:00Z", 9), clip("b", "2026-01-02T00:00:00Z")])
    clips, total = s.top_clips("1", None, None, 10, 0)
    assert total == 2
    assert clips[0].id == "a" and clips[0].view_count == 9


def test_bucket_counts_zero_fills_and_counts_by_utc_day(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [
        clip("a", "2026-01-01T23:59:59Z"),
        clip("b", "2026-01-02T00:00:00Z"),
        clip("c", "2026-01-02T10:00:00Z"),
    ])
    days = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 4), "day")
    assert [(b.key, b.count) for b in days] == [
        ("2026-01-01", 1), ("2026-01-02", 2), ("2026-01-03", 0), ("2026-01-04", 0)
    ]
    months = s.bucket_counts("1", date(2025, 12, 15), date(2026, 2, 1), "month")
    assert [(b.key, b.count) for b in months] == [("2025-12", 0), ("2026-01", 3), ("2026-02", 0)]


def test_bucket_not_ready_while_any_overlapping_leaf_pending(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 1, 16)), (dt(2026, 1, 16), dt(2026, 2, 1))])
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 1, 16), dt(2026, 3, 1), False)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0]
    assert b.state != "exact"
    s.mark_done("1", dt(2026, 1, 16), dt(2026, 2, 1), dt(2026, 3, 1), False)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0]
    assert b.state == "exact"


def test_bucket_not_ready_with_no_windows(tmp_path):
    s = make(tmp_path)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "day")[0]
    assert b.state != "exact"


def test_split_parent_is_not_a_leaf(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 1, 3))])
    s.mark_split("1", dt(2026, 1, 1), dt(2026, 1, 3), [
        (dt(2026, 1, 1), dt(2026, 1, 2)), (dt(2026, 1, 2), dt(2026, 1, 3))
    ])
    day = lambda: s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "day")[0]
    assert day().state != "exact"
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 1, 2), dt(2026, 3, 1), False)
    assert day().state == "exact"
    p = s.progress("1")
    assert p.windows_total == 2 and p.windows_done == 1


def test_next_pending_returns_latest_end_first(tmp_path):
    s = make(tmp_path)
    assert s.next_pending("1") is None
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1)), (dt(2026, 2, 1), dt(2026, 3, 1))])
    w = s.next_pending("1")
    assert w.end == dt(2026, 3, 1) and w.status == "pending" and w.fetched_at is None
    s.add_windows("1", [(dt(2026, 2, 1), dt(2026, 3, 1))])
    assert s.progress("1").windows_total == 2


def test_reset_nonfinal_keeps_old_done_windows(tmp_path):
    s = make(tmp_path)
    old = (dt(2026, 1, 1), dt(2026, 2, 1))
    new = (dt(2026, 2, 1), dt(2026, 3, 1))
    s.add_windows("1", [old, new])
    s.mark_done("1", *old, dt(2026, 5, 1), False)
    s.mark_done("1", *new, dt(2026, 3, 2), True)
    s.reset_windows("1", "nonfinal", dt(2026, 5, 2), timedelta(days=2))
    w = s.next_pending("1")
    assert (w.start, w.end) == new and w.truncated is False and w.fetched_at is None
    assert s.progress("1").windows_done == 1


def test_reset_all_resets_every_done_leaf(tmp_path):
    s = make(tmp_path)
    old = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [old])
    s.mark_done("1", *old, dt(2026, 5, 1), True)
    s.reset_windows("1", "all", dt(2026, 5, 2), timedelta(days=2))
    assert s.progress("1").windows_done == 0
    assert s.next_pending("1") is not None


def test_top_clips_pages_and_totals(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [
        clip("a", "2026-01-01T00:00:00Z", 5),
        clip("b", "2026-01-02T00:00:00Z", 9),
        clip("c", "2026-01-03T23:59:59Z", 7),
        clip("d", "2026-01-04T00:00:00Z", 100),
    ])
    page, total = s.top_clips("1", date(2026, 1, 1), date(2026, 1, 3), 2, 0)
    assert total == 3 and [c.id for c in page] == ["b", "c"]
    page, total = s.top_clips("1", date(2026, 1, 1), date(2026, 1, 3), 2, 2)
    assert [c.id for c in page] == ["a"]
    _, total = s.top_clips("1", None, None, 10, 0)
    assert total == 4


def test_state_survives_reopening_store(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1))])
    s.upsert_clips("1", [clip("a", "2026-01-01T00:00:00Z")])
    s2 = make(tmp_path)
    assert s2.next_pending("1") is not None
    assert s2.top_clips("1", None, None, 10, 0)[1] == 1


def test_reset_keeps_buckets_ready(tmp_path):
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 1, 20), False)
    s.reset_windows("1", "all", dt(2026, 1, 21), timedelta(days=2))
    assert s.progress("1").windows_done == 0
    (b,) = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")
    assert b.state == "exact"
    (d,) = s.bucket_counts("1", date(2026, 1, 5), date(2026, 1, 5), "day")
    assert d.state == "exact"


def test_split_children_make_bucket_not_ready_until_fetched(tmp_path):
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 1, 20), False)
    s.reset_windows("1", "all", dt(2026, 1, 21), timedelta(days=2))
    s.mark_split("1", *month, [(dt(2026, 1, d), dt(2026, 1, d + 1)) for d in range(1, 31)] + [(dt(2026, 1, 31), dt(2026, 2, 1))])
    day = lambda: s.bucket_counts("1", date(2026, 1, 5), date(2026, 1, 5), "day")[0]
    assert day().state != "exact"
    s.mark_done("1", dt(2026, 1, 5), dt(2026, 1, 6), dt(2026, 1, 21), False)
    assert day().state == "exact"


def test_split_windows_lists_split_parents(tmp_path):
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month, (dt(2026, 2, 1), dt(2026, 3, 1))])
    s.mark_split("1", *month, [(dt(2026, 1, 1), dt(2026, 1, 2))])
    assert s.split_windows("1") == [month]


OLD_SCHEMA = """
CREATE TABLE streamers (broadcaster_id TEXT PRIMARY KEY, login TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, account_created TEXT NOT NULL);
CREATE TABLE clips (id TEXT PRIMARY KEY, broadcaster_id TEXT NOT NULL, url TEXT NOT NULL,
    title TEXT NOT NULL, thumbnail_url TEXT NOT NULL, view_count INTEGER NOT NULL,
    duration REAL NOT NULL, creator_name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE windows (broadcaster_id TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', fetched_at TEXT, truncated INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (broadcaster_id, start, "end"));
INSERT INTO windows VALUES ('1', '2026-01-01T00:00:00Z', '2026-02-01T00:00:00Z', 'done', '2026-03-01T00:00:00Z', 0);
INSERT INTO windows VALUES ('1', '2026-02-01T00:00:00Z', '2026-03-01T00:00:00Z', 'split', NULL, 0);
INSERT INTO windows VALUES ('1', '2026-02-01T00:00:00Z', '2026-02-02T00:00:00Z', 'done', '2026-03-01T00:00:00Z', 1);
INSERT INTO windows VALUES ('1', '2026-02-02T00:00:00Z', '2026-02-03T00:00:00Z', 'pending', NULL, 0);
INSERT INTO clips VALUES ('a', '1', 'u', 't', 'th', 5, 1.0, 'c', '2026-01-05T00:00:00Z');
"""


def old_db(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.close()
    return path


def user_version(path):
    import sqlite3
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()


def test_old_database_resets_done_leaves_once_and_keeps_clips(tmp_path):
    path = old_db(tmp_path)
    s = Store(path)
    assert user_version(path) == SCHEMA_VERSION
    p = s.progress("1")
    assert p.windows_done == 0 and p.windows_total == 3 and p.capped == 0 and p.clips == 1
    (b,) = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")
    assert b.count == 1 and b.state != "exact"
    assert s.split_windows("1") == [(dt(2026, 2, 1), dt(2026, 3, 1))]
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 11, 1), False)
    s2 = Store(path)
    assert s2.progress("1").windows_done == 1
    assert s2.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0].state == "exact"


def test_fresh_database_starts_at_current_version(tmp_path):
    s = make(tmp_path)
    assert user_version(tmp_path / "s.db") == SCHEMA_VERSION
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 3, 1), False)
    make(tmp_path)
    assert s.progress("1").windows_done == 1


def _mixed(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [
        (dt(2025, 12, 1), dt(2026, 1, 1)),
        (dt(2026, 1, 1), dt(2026, 2, 1)),
        (dt(2026, 1, 10), dt(2026, 1, 11)),
        (dt(2025, 12, 5), dt(2025, 12, 6)),
        (dt(2026, 1, 10, 3), dt(2026, 1, 10, 4)),
    ])
    return s


def test_next_pending_returns_all_months_before_any_day(tmp_path):
    s = _mixed(tmp_path)
    order = []
    while (w := s.next_pending("1")) is not None:
        order.append((w.start, w.end))
        s.mark_done("1", w.start, w.end, dt(2026, 3, 1), False)
    assert order == [
        (dt(2026, 1, 1), dt(2026, 2, 1)),
        (dt(2025, 12, 1), dt(2026, 1, 1)),
        (dt(2026, 1, 10), dt(2026, 1, 11)),
        (dt(2026, 1, 10, 3), dt(2026, 1, 10, 4)),
        (dt(2025, 12, 5), dt(2025, 12, 6)),
    ]


def test_next_pending_skips_days_outside_allowed_years(tmp_path):
    s = _mixed(tmp_path)
    for _ in range(2):
        w = s.next_pending("1", {2026})
        s.mark_done("1", w.start, w.end, dt(2026, 3, 1), False)
    seen = []
    while (w := s.next_pending("1", {2026})) is not None:
        seen.append(w.start)
        s.mark_done("1", w.start, w.end, dt(2026, 3, 1), False)
    assert seen == [dt(2026, 1, 10), dt(2026, 1, 10, 3)]
    assert s.next_pending("1", set()) is None
    assert s.next_pending("1").start == dt(2025, 12, 5)


def test_coarse_only_never_returns_day_windows(tmp_path):
    s = _mixed(tmp_path)
    for _ in range(2):
        w = s.next_pending("1", None, True)
        s.mark_done("1", w.start, w.end, dt(2026, 3, 1), False)
    assert s.next_pending("1", None, True) is None
    assert s.next_pending("1") is not None


def test_exact_years_default_is_current_and_previous(tmp_path):
    s = make(tmp_path)
    assert s.exact_years("1", 2026) == {2026, 2025}


def test_exact_years_overrides_enable_and_disable(tmp_path):
    s = make(tmp_path)
    s.set_exact_year("1", 2023, True)
    s.set_exact_year("1", 2025, False)
    assert s.exact_years("1", 2026) == {2026, 2023}
    s.set_exact_year("1", 2025, True)
    s.set_exact_year("1", 2023, False)
    assert s.exact_years("1", 2026) == {2026, 2025}
    assert s.exact_years("2", 2026) == {2026, 2025}


def test_progress_excludes_out_of_scope_fine_windows(tmp_path):
    s = _mixed(tmp_path)
    assert s.progress("1").windows_total == 5
    p = s.progress("1", {2026})
    assert p.windows_total == 4
    s.mark_done("1", dt(2025, 12, 5), dt(2025, 12, 6), dt(2026, 3, 1), False)
    p = s.progress("1", {2026})
    assert p.windows_total == 5 and p.windows_done == 1
    s.mark_split("1", dt(2025, 12, 1), dt(2026, 1, 1), [])
    assert s.progress("1", {2026}).windows_total == 4


def test_version_2_database_gets_years_table_without_reset(tmp_path):
    import sqlite3
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 3, 1), False)
    path = tmp_path / "s.db"
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE streamer_years")
    conn.execute("PRAGMA user_version = 2")
    conn.close()
    s2 = Store(path)
    assert user_version(path) == SCHEMA_VERSION == 4
    assert s2.progress("1").windows_done == 1
    s2.set_exact_year("1", 2020, True)
    assert 2020 in s2.exact_years("1", 2026)


def _state(s, day=date(2026, 1, 1), g="month"):
    return s.bucket_counts("1", day, day, g)[0]


def test_bucket_state_exact_when_all_leaves_fetched_and_not_truncated(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [clip("a", "2026-01-02T00:00:00Z")])
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1))])
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 3, 1), False)
    b = _state(s)
    assert (b.state, b.count) == ("exact", 1)


def test_bucket_state_approximate_when_a_child_window_is_pending(tmp_path):
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 3, 1), True)
    s.upsert_clips("1", [clip("a", "2026-01-02T00:00:00Z")])
    s.mark_split("1", *month, [(dt(2026, 1, 1), dt(2026, 1, 16)), (dt(2026, 1, 16), dt(2026, 2, 1))])
    b = _state(s)
    assert (b.state, b.count) == ("approximate", 1)


def test_bucket_state_approximate_when_leaf_truncated(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 5, 3), dt(2026, 1, 5, 4))])
    s.mark_done("1", dt(2026, 1, 5, 3), dt(2026, 1, 5, 4), dt(2026, 3, 1), True)
    s.upsert_clips("1", [clip("a", "2026-01-05T03:10:00Z")])
    assert _state(s, date(2026, 1, 5), "day").state == "approximate"
    assert _state(s).state == "approximate"


def test_bucket_state_empty_when_not_exact_and_no_clips(tmp_path):
    s = make(tmp_path)
    assert _state(s).state == "empty"
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1))])
    assert _state(s).state == "empty"


def test_bucket_with_no_leaf_and_clips_is_approximate(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [clip("a", "2026-01-02T00:00:00Z")])
    assert _state(s).state == "approximate"


def test_exact_bucket_with_zero_clips_is_exact(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1))])
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 3, 1), False)
    b = _state(s)
    assert (b.state, b.count) == ("exact", 0)


def test_years_summary_states_and_enabled_flags(tmp_path):
    s = make(tmp_path)
    y24 = (dt(2024, 1, 1), dt(2025, 1, 1))
    s.add_windows("1", [y24, (dt(2025, 1, 1), dt(2025, 2, 1)), (dt(2025, 2, 1), dt(2025, 3, 1))])
    s.mark_done("1", *y24, dt(2026, 1, 1), False)
    s.mark_done("1", dt(2025, 1, 1), dt(2025, 2, 1), dt(2026, 1, 1), False)
    s.upsert_clips("1", [
        clip("a", "2024-06-01T00:00:00Z"),
        clip("b", "2024-12-31T23:59:59Z"),
        clip("c", "2025-01-10T00:00:00Z"),
        clip("d", "2026-05-01T00:00:00Z"),
    ])
    s.set_exact_year("1", 2023, True)
    s.set_exact_year("1", 2025, False)
    got = s.years_summary("1", 2022, 2026, 2026)
    assert [(y.year, y.enabled, y.state, y.clips) for y in got] == [
        (2022, False, "empty", 0),
        (2023, True, "empty", 0),
        (2024, False, "exact", 2),
        (2025, False, "approximate", 1),
        (2026, True, "approximate", 1),
    ]


def test_years_summary_capped_leaf_is_approximate(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2024, 3, 1, 5), dt(2024, 3, 1, 6)), (dt(2024, 1, 1), dt(2024, 3, 1, 5))])
    s.mark_done("1", dt(2024, 3, 1, 5), dt(2024, 3, 1, 6), dt(2026, 1, 1), True)
    s.mark_done("1", dt(2024, 1, 1), dt(2024, 3, 1, 5), dt(2026, 1, 1), False)
    s.upsert_clips("1", [clip("a", "2024-03-01T05:30:00Z")])
    (y,) = s.years_summary("1", 2024, 2024, 2026)
    assert y.state == "approximate"


def test_range_exact_requires_every_month_exact(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 2, 1)), (dt(2026, 2, 1), dt(2026, 3, 1))])
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 4, 1), False)
    created, today = date(2020, 1, 1), date(2026, 2, 20)
    assert s.range_exact("1", date(2026, 1, 5), date(2026, 1, 20), created, today) is True
    assert s.range_exact("1", date(2026, 1, 5), date(2026, 2, 20), created, today) is False
    s.mark_done("1", dt(2026, 2, 1), dt(2026, 3, 1), dt(2026, 4, 1), False)
    assert s.range_exact("1", date(2026, 1, 5), date(2026, 2, 20), created, today) is True


def test_range_exact_clamps_to_account_and_today(tmp_path):
    s = make(tmp_path)
    created, today = date(2026, 1, 10), date(2026, 1, 20)
    assert s.range_exact("1", date(2025, 1, 1), date(2025, 6, 1), created, today) is True
    assert s.range_exact("1", date(2026, 2, 1), None, created, today) is True
    assert s.range_exact("1", None, None, created, today) is False


def test_top_clips_newest_orders_by_created_at(tmp_path):
    s = make(tmp_path)
    s.upsert_clips("1", [
        clip("a", "2026-01-01T00:00:00Z", 50),
        clip("b", "2026-01-03T00:00:00Z", 1),
        clip("c", "2026-01-02T00:00:00Z", 9),
    ])
    clips, _ = s.top_clips("1", None, None, 10, 0, sort="newest")
    assert [c.id for c in clips] == ["b", "c", "a"]
    clips, _ = s.top_clips("1", None, None, 10, 0)
    assert [c.id for c in clips] == ["a", "c", "b"]
    import pytest
    with pytest.raises(ValueError):
        s.top_clips("1", None, None, 10, 0, sort="oldest")


def test_seed_inserts_once_and_only_once(tmp_path):
    s = make(tmp_path)
    assert s.watch_list() == []
    assert s.seed_watchlist_once(["Alpha", "beta"]) is True
    entries = s.watch_list()
    assert [e.login for e in entries] == ["alpha", "beta"]
    assert all(e.broadcaster_id is None and not e.paused and e.last_refreshed is None for e in entries)
    s.watch_remove("alpha")
    assert s.seed_watchlist_once(["alpha"]) is False
    assert Store(tmp_path / "s.db").seed_watchlist_once(["alpha"]) is False
    assert [e.login for e in s.watch_list()] == ["beta"]
    assert SEED_WATCHLIST == ["stableronaldo", "jasontheween", "arky", "marlon", "yugi", "ludwig"]


def test_watch_add_is_idempotent_and_remove_works(tmp_path):
    s = make(tmp_path)
    s.watch_add("jason", None)
    s.watch_add("jason", "7")
    s.watch_add("jason", "8")
    (e,) = s.watch_list()
    assert isinstance(e, WatchEntry) and e.login == "jason" and e.broadcaster_id == "7"
    s.watch_remove("nobody")
    s.watch_remove("jason")
    assert s.watch_list() == []


def test_paused_and_refreshed_round_trip(tmp_path):
    s = make(tmp_path)
    s.watch_add("jason", None)
    s.watch_set_paused("jason", True)
    s.watch_set_broadcaster("jason", "9")
    s.watch_mark_refreshed("jason", dt(2026, 11, 1, 5))
    (e,) = s.watch_list()
    assert e.paused is True and e.broadcaster_id == "9" and e.last_refreshed == dt(2026, 11, 1, 5)
    s.watch_set_paused("jason", False)
    s.watch_set_paused("ghost", True)
    assert s.watch_list()[0].paused is False
    assert len(s.watch_list()) == 1


def test_version_3_database_gets_watchlist_tables(tmp_path):
    import sqlite3
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 3, 1), False)
    path = tmp_path / "s.db"
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE watchlist")
    conn.execute("DROP TABLE meta")
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
    conn.close()
    s2 = Store(path)
    assert user_version(path) == SCHEMA_VERSION == 4
    assert s2.progress("1").windows_done == 1
    assert s2.watch_list() == []
    assert s2.seed_watchlist_once(["a"]) is True


def test_bucket_has_no_ready_field(tmp_path):
    s = make(tmp_path)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0]
    assert not hasattr(b, "ready")
    assert b.state in ("exact", "approximate", "empty")
