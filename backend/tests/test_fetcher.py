from datetime import date, datetime, timedelta, timezone

import pytest

from fetcher import GRACE, month_windows, plan_windows, run_fetch, split_window
from store import Store
from twitch import Clip, ClipsResult, TwitchError, User

UTC = timezone.utc


def dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def clip(cid, created):
    return Clip(cid, f"https://clips.twitch.tv/{cid}", cid, "https://example/t.jpg", 1, 10.0, "c", created)


class FakeTwitch:
    def __init__(self, results=None, default=None, fail_on=None):
        self.results = results or {}
        self.default = default or ClipsResult([], False)
        self.fail_on = fail_on
        self.calls = []

    def fetch_window(self, broadcaster_id, start, end):
        self.calls.append((start, end))
        if self.fail_on == len(self.calls):
            raise TwitchError("boom")
        return self.results.get((start, end), self.default)


def user(created):
    return User("1", "streamer", "Streamer", created)


def make(tmp_path):
    return Store(tmp_path / "s.db")


def test_month_windows_cover_account_month_through_now():
    got = month_windows(dt(2025, 11, 15), dt(2026, 2, 3))
    assert got == [
        (dt(2025, 11, 1), dt(2025, 12, 1)),
        (dt(2025, 12, 1), dt(2026, 1, 1)),
        (dt(2026, 1, 1), dt(2026, 2, 1)),
        (dt(2026, 2, 1), dt(2026, 3, 1)),
    ]


def test_split_window_month_to_days_day_to_hours_hour_to_nothing():
    days = split_window(dt(2026, 2, 1), dt(2026, 3, 1))
    assert len(days) == 28
    assert days[0] == (dt(2026, 2, 1), dt(2026, 2, 2))
    assert days[-1] == (dt(2026, 2, 28), dt(2026, 3, 1))
    hours = split_window(dt(2026, 2, 1), dt(2026, 2, 2))
    assert len(hours) == 24
    assert hours[1] == (dt(2026, 2, 1, 1), dt(2026, 2, 1, 2))
    assert split_window(dt(2026, 2, 1, 5), dt(2026, 2, 1, 6)) == []


def test_run_fetch_processes_most_recent_window_first(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 3, 10))
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1")
    assert [s for s, _ in twitch.calls] == [dt(2026, 3, 1), dt(2026, 2, 1), dt(2026, 1, 1)]


def test_capped_window_is_split_and_children_fetched(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 2, 5)), "full", dt(2026, 2, 10))
    month = (dt(2026, 2, 1), dt(2026, 3, 1))
    day = (dt(2026, 2, 3), dt(2026, 2, 4))
    twitch = FakeTwitch(
        results={
            month: ClipsResult([clip("a", "2026-02-03T05:00:00Z")], True),
            day: ClipsResult([clip("b", "2026-02-03T06:00:00Z")], False),
        }
    )
    run_fetch(store, twitch, "1")
    assert len(twitch.calls) == 1 + 28
    p = store.progress("1")
    assert p.windows_total == 28 and p.windows_done == 28 and p.capped == 0
    assert p.clips == 2
    b = store.bucket_counts("1", date(2026, 2, 1), date(2026, 2, 28), "day")
    assert all(x.ready for x in b)


def test_capped_hour_is_marked_truncated_not_dropped(tmp_path):
    store = make(tmp_path)
    hour = (dt(2026, 2, 3, 4), dt(2026, 2, 3, 5))
    store.add_windows("1", [hour])
    twitch = FakeTwitch(results={hour: ClipsResult([clip("a", "2026-02-03T04:10:00Z")], True)})
    run_fetch(store, twitch, "1")
    p = store.progress("1")
    assert p.capped == 1 and p.windows_done == 1 and p.clips == 1
    assert len(twitch.calls) == 1


def test_run_fetch_resumes_only_pending_windows(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 2, 10))
    store.mark_done("1", dt(2026, 2, 1), dt(2026, 3, 1), dt(2026, 2, 10), False)
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1")
    assert twitch.calls == [(dt(2026, 1, 1), dt(2026, 2, 1))]


def test_auto_plan_refetches_recent_but_not_final_windows(tmp_path):
    store = make(tmp_path)
    now = dt(2026, 3, 10)
    plan_windows(store, user(dt(2026, 1, 5)), "auto", now)
    store.mark_done("1", dt(2026, 1, 1), dt(2026, 2, 1), dt(2026, 2, 1) + GRACE + timedelta(hours=1), False)
    store.mark_done("1", dt(2026, 2, 1), dt(2026, 3, 1), dt(2026, 3, 2), False)
    store.mark_done("1", dt(2026, 3, 1), dt(2026, 4, 1), dt(2026, 3, 9), False)
    plan_windows(store, user(dt(2026, 1, 5)), "auto", now)
    assert store.next_pending("1").start == dt(2026, 3, 1)
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1")
    assert sorted(s for s, _ in twitch.calls) == [dt(2026, 2, 1), dt(2026, 3, 1)]


def test_full_plan_resets_everything(tmp_path):
    store = make(tmp_path)
    now = dt(2026, 3, 10)
    plan_windows(store, user(dt(2026, 1, 5)), "auto", now)
    for s, e in month_windows(dt(2026, 1, 5), now):
        store.mark_done("1", s, e, dt(2026, 3, 9), False)
    plan_windows(store, user(dt(2026, 1, 5)), "full", now)
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1")
    assert len(twitch.calls) == 3


def test_plan_windows_rejects_unknown_mode(tmp_path):
    with pytest.raises(ValueError):
        plan_windows(make(tmp_path), user(dt(2026, 1, 5)), "bogus", dt(2026, 3, 10))


def test_account_created_this_month_yields_one_window_and_zero_clips_is_ready(tmp_path):
    store = make(tmp_path)
    now = dt(2026, 3, 10)
    plan_windows(store, user(dt(2026, 3, 2)), "auto", now)
    assert store.progress("1").windows_total == 1
    run_fetch(store, FakeTwitch(), "1")
    (b,) = store.bucket_counts("1", date(2026, 3, 1), date(2026, 3, 31), "month")
    assert b.ready and b.count == 0


def test_refetching_clips_does_not_double_count(tmp_path):
    store = make(tmp_path)
    now = dt(2026, 3, 10)
    month = (dt(2026, 3, 1), dt(2026, 4, 1))
    twitch = FakeTwitch(results={month: ClipsResult([clip("a", "2026-03-03T01:00:00Z")], False)})
    plan_windows(store, user(dt(2026, 3, 2)), "auto", now)
    run_fetch(store, twitch, "1")
    plan_windows(store, user(dt(2026, 3, 2)), "full", now)
    run_fetch(store, twitch, "1")
    assert store.progress("1").clips == 1


def test_twitch_error_propagates_and_window_stays_pending(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 2, 10))
    twitch = FakeTwitch(fail_on=2)
    with pytest.raises(TwitchError):
        run_fetch(store, twitch, "1")
    assert store.progress("1").windows_done == 1
    assert store.next_pending("1").start == dt(2026, 1, 1)
