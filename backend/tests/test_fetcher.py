from datetime import date, datetime, timedelta, timezone

import pytest

from fetcher import GRACE, TRUNCATION_THRESHOLD, month_windows, plan_windows, run_fetch, split_window
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
    assert all(x.state == "exact" for x in b)


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
    assert b.state == "exact" and b.count == 0


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


class HelixLikeTwitch:
    def __init__(self, clips, cap=1000):
        self.clips = clips
        self.cap = cap
        self.calls = []

    def fetch_window(self, broadcaster_id, start, end):
        self.calls.append((start, end))
        s, e = start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")
        inside = [c for c in self.clips if s <= c.created_at < e]
        return ClipsResult(inside[: self.cap], False)


def spread(prefix, day, n, hours=24):
    return [clip(f"{prefix}{i}", f"2026-02-{day:02d}T{i % hours:02d}:{i % 60:02d}:00Z") for i in range(n)]


def busy_february():
    clips = []
    for d in range(1, 29):
        clips += spread(f"d{d}-", d, 2400 if d == 3 else 40)
    return clips


@pytest.mark.parametrize("cap", [1000, 954])
def test_silently_capped_month_splits_to_days_and_hours_and_counts_exactly(tmp_path, cap):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 2, 1)), "full", dt(2026, 3, 1))
    clips = busy_february()
    twitch = HelixLikeTwitch(clips, cap=cap)
    run_fetch(store, twitch, "1", now=lambda: dt(2026, 3, 5))
    p = store.progress("1")
    assert p.clips == len(clips) == 27 * 40 + 2400
    assert p.capped == 0
    assert (dt(2026, 2, 1), dt(2026, 3, 1)) in twitch.calls
    assert (dt(2026, 2, 3), dt(2026, 2, 4)) in twitch.calls
    assert (dt(2026, 2, 3, 5), dt(2026, 2, 3, 6)) in twitch.calls
    assert (dt(2026, 2, 4, 5), dt(2026, 2, 4, 6)) not in twitch.calls
    feb3 = store.bucket_counts("1", date(2026, 2, 3), date(2026, 2, 3), "day")[0]
    assert feb3.count == 2400 and feb3.state == "exact"


def test_window_below_threshold_is_not_split(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 2, 1)), "full", dt(2026, 3, 1))
    clips = spread("a", 3, TRUNCATION_THRESHOLD - 1)
    twitch = HelixLikeTwitch(clips)
    run_fetch(store, twitch, "1", now=lambda: dt(2026, 3, 5))
    assert len(twitch.calls) == 2
    assert store.progress("1").clips == TRUNCATION_THRESHOLD - 1


def test_hour_at_threshold_is_marked_truncated(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 2, 1)), "full", dt(2026, 3, 1))
    clips = spread("h", 3, TRUNCATION_THRESHOLD + 50, hours=1)
    twitch = HelixLikeTwitch(clips)
    run_fetch(store, twitch, "1", now=lambda: dt(2026, 3, 5))
    p = store.progress("1")
    assert p.capped == 1
    assert p.clips == TRUNCATION_THRESHOLD + 50


def test_split_of_current_month_and_day_skips_the_future(tmp_path):
    store = make(tmp_path)
    now = dt(2026, 2, 10, 12)
    plan_windows(store, user(dt(2026, 2, 1)), "auto", now)
    clips = spread("x", 10, 2000, hours=12)
    twitch = HelixLikeTwitch(clips)
    run_fetch(store, twitch, "1", now=lambda: now)
    assert all(s < now for s, _ in twitch.calls)
    assert (dt(2026, 2, 10, 11), dt(2026, 2, 10, 12)) in twitch.calls
    assert store.progress("1").clips == 2000
    later = dt(2026, 2, 11, 3)
    plan_windows(store, user(dt(2026, 2, 1)), "auto", later)
    twitch.calls.clear()
    run_fetch(store, twitch, "1", now=lambda: later)
    assert (dt(2026, 2, 11), dt(2026, 2, 12)) in twitch.calls
    assert (dt(2026, 2, 10, 12), dt(2026, 2, 10, 13)) in twitch.calls
    assert all(s < later for s, _ in twitch.calls)


def test_run_fetch_stops_between_windows(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 3, 10))
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1", should_stop=lambda: len(twitch.calls) >= 1)
    assert len(twitch.calls) == 1
    assert store.progress("1").windows_done == 1
    assert store.next_pending("1").start == dt(2026, 2, 1)


def test_run_fetch_finishes_when_only_out_of_scope_windows_remain(tmp_path):
    store = make(tmp_path)
    store.add_windows("1", [(dt(2020, 1, 1), dt(2020, 1, 2)), (dt(2026, 1, 1), dt(2026, 2, 1))])
    twitch = FakeTwitch()
    run_fetch(store, twitch, "1", allowed_years=lambda: {2026})
    assert twitch.calls == [(dt(2026, 1, 1), dt(2026, 2, 1))]
    assert store.next_pending("1") is not None


def test_run_fetch_picks_up_year_enabled_mid_run(tmp_path):
    store = make(tmp_path)
    store.add_windows("1", [(dt(2020, 1, 1), dt(2020, 1, 2)), (dt(2026, 1, 1), dt(2026, 2, 1))])
    allowed = {2026}

    class Enabling(FakeTwitch):
        def fetch_window(self, broadcaster_id, start, end):
            allowed.add(2020)
            return super().fetch_window(broadcaster_id, start, end)

    twitch = Enabling()
    run_fetch(store, twitch, "1", allowed_years=lambda: allowed)
    assert [s for s, _ in twitch.calls] == [dt(2026, 1, 1), dt(2020, 1, 1)]


def test_plan_resume_adds_windows_without_resetting_done(tmp_path):
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 1, 20))
    run_fetch(store, FakeTwitch(), "1")
    plan_windows(store, user(dt(2026, 1, 5)), "resume", dt(2026, 2, 10))
    p = store.progress("1")
    assert p.windows_done == 1 and p.windows_total == 2
    assert store.next_pending("1").start == dt(2026, 2, 1)


def test_delay_is_applied_between_windows(tmp_path, monkeypatch):
    import fetcher
    store = make(tmp_path)
    plan_windows(store, user(dt(2026, 1, 5)), "full", dt(2026, 3, 10))
    sleeps = []
    monkeypatch.setattr(fetcher.time, "sleep", sleeps.append)
    run_fetch(store, FakeTwitch(), "1", delay=0.5)
    assert sleeps == [0.5, 0.5]
