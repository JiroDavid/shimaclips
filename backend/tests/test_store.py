from datetime import date, datetime, timedelta, timezone

from store import Store
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
