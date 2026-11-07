from datetime import date, datetime, timedelta, timezone

from store import SCHEMA_VERSION, Store
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
    assert b.ready is False
    s.mark_done("1", dt(2026, 1, 16), dt(2026, 2, 1), dt(2026, 3, 1), False)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0]
    assert b.ready is True


def test_bucket_not_ready_with_no_windows(tmp_path):
    s = make(tmp_path)
    b = s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "day")[0]
    assert b.ready is False


def test_split_parent_is_not_a_leaf(tmp_path):
    s = make(tmp_path)
    s.add_windows("1", [(dt(2026, 1, 1), dt(2026, 1, 3))])
    s.mark_split("1", dt(2026, 1, 1), dt(2026, 1, 3), [
        (dt(2026, 1, 1), dt(2026, 1, 2)), (dt(2026, 1, 2), dt(2026, 1, 3))
    ])
    day = lambda: s.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "day")[0]
    assert day().ready is False
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 1, 2), dt(2026, 3, 1), False)
    assert day().ready is True
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
    assert b.ready is True
    (d,) = s.bucket_counts("1", date(2026, 1, 5), date(2026, 1, 5), "day")
    assert d.ready is True


def test_split_children_make_bucket_not_ready_until_fetched(tmp_path):
    s = make(tmp_path)
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 1, 20), False)
    s.reset_windows("1", "all", dt(2026, 1, 21), timedelta(days=2))
    s.mark_split("1", *month, [(dt(2026, 1, d), dt(2026, 1, d + 1)) for d in range(1, 31)] + [(dt(2026, 1, 31), dt(2026, 2, 1))])
    day = lambda: s.bucket_counts("1", date(2026, 1, 5), date(2026, 1, 5), "day")[0]
    assert day().ready is False
    s.mark_done("1", dt(2026, 1, 5), dt(2026, 1, 6), dt(2026, 1, 21), False)
    assert day().ready is True


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
    assert b.count == 1 and b.ready is False
    assert s.split_windows("1") == [(dt(2026, 2, 1), dt(2026, 3, 1))]
    s.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 11, 1), False)
    s2 = Store(path)
    assert s2.progress("1").windows_done == 1
    assert s2.bucket_counts("1", date(2026, 1, 1), date(2026, 1, 1), "month")[0].ready is True


def test_fresh_database_starts_at_current_version(tmp_path):
    s = make(tmp_path)
    assert user_version(tmp_path / "s.db") == SCHEMA_VERSION
    month = (dt(2026, 1, 1), dt(2026, 2, 1))
    s.add_windows("1", [month])
    s.mark_done("1", *month, dt(2026, 3, 1), False)
    make(tmp_path)
    assert s.progress("1").windows_done == 1
