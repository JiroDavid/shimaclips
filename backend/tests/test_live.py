import threading
from datetime import date, datetime, timezone

import pytest

from live import LiveClips
from store import Store
from twitch import Clip, TwitchError

UTC = timezone.utc
CREATED = datetime(2020, 1, 1, tzinfo=UTC)
TODAY = date(2026, 3, 1)


def mk(i, views=5, created="2026-01-02T00:00:00Z"):
    return Clip(f"c{i}", f"https://clips.twitch.tv/c{i}", f"clip {i}", "t.jpg", views, 10.0, "x", created)


class FakeTwitch:
    def __init__(self, clips=(), error=None, gate=None):
        self.clips = list(clips)
        self.error = error
        self.gate = gate
        self.calls = []

    def fetch_top(self, broadcaster_id, start, end, limit):
        self.calls.append((broadcaster_id, start, end, limit))
        if self.gate:
            self.gate.wait(5)
        if self.error:
            raise self.error
        return self.clips[:limit]


class Streamer:
    broadcaster_id = "1"
    account_created = CREATED


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "l.db")


def live_for(store, fake, clock=None, ttl=120.0):
    return LiveClips(store, lambda: fake, ttl=ttl, clock=clock or Clock())


def test_not_exact_range_fetches_from_twitch_and_stores(store):
    fake = FakeTwitch([mk(1), mk(2)])
    live = live_for(store, fake)
    exact = live.ensure(Streamer, date(2026, 1, 1), date(2026, 1, 31), 10, TODAY)
    assert exact is False
    assert fake.calls == [(
        "1", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC), 10,
    )]
    assert store.top_clips("1", None, None, 10, 0)[1] == 2


def test_all_time_passes_none_bounds_and_caps_limit(store):
    fake = FakeTwitch()
    live_for(store, fake).ensure(Streamer, None, None, 5000, TODAY)
    assert fake.calls == [("1", None, None, 1000)]


def test_exact_range_never_calls_twitch(store):
    store.add_windows("1", [(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))])
    store.mark_done("1", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC),
                    datetime(2026, 3, 1, tzinfo=UTC), False)
    fake = FakeTwitch([mk(1)])
    assert live_for(store, fake).ensure(Streamer, date(2026, 1, 1), date(2026, 1, 31), 10, TODAY) is True
    assert fake.calls == []


def test_repeat_within_ttl_does_not_call_twitch_again(store):
    fake = FakeTwitch([mk(1)])
    clock = Clock()
    live = live_for(store, fake, clock)
    args = (Streamer, date(2026, 1, 1), date(2026, 1, 31), 10, TODAY)
    live.ensure(*args)
    clock.t += 2
    assert live.ensure(*args) is False
    assert live.ensure(Streamer, date(2026, 1, 1), date(2026, 1, 31), 5, TODAY) is False
    assert len(fake.calls) == 1


def test_larger_need_after_ttl_or_bigger_need_refetches(store):
    fake = FakeTwitch([mk(1)])
    clock = Clock()
    live = live_for(store, fake, clock, ttl=60)
    args = (Streamer, date(2026, 1, 1), date(2026, 1, 31))
    live.ensure(*args, 10, TODAY)
    live.ensure(*args, 20, TODAY)
    assert len(fake.calls) == 2
    clock.t += 61
    live.ensure(*args, 20, TODAY)
    assert len(fake.calls) == 3
    live.ensure(Streamer, date(2026, 1, 1), date(2026, 1, 30), 20, TODAY)
    assert len(fake.calls) == 4


def test_concurrent_identical_calls_share_one_fetch(store):
    gate = threading.Event()
    fake = FakeTwitch([mk(1)], gate=gate)
    live = live_for(store, fake)
    results = []

    def run():
        results.append(live.ensure(Streamer, date(2026, 1, 1), date(2026, 1, 31), 10, TODAY))

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(200):
        if fake.calls:
            break
        threading.Event().wait(0.01)
    gate.set()
    for t in threads:
        t.join(5)
    assert results == [False] * 4
    assert len(fake.calls) == 1


def test_twitch_error_propagates_and_is_not_memoized(store):
    fake = FakeTwitch(error=TwitchError("boom"))
    live = live_for(store, fake)
    args = (Streamer, date(2026, 1, 1), date(2026, 1, 31), 10, TODAY)
    with pytest.raises(TwitchError):
        live.ensure(*args)
    fake.error = None
    live.ensure(*args)
    assert len(fake.calls) == 2


def wait_for(cond, tries=300):
    for _ in range(tries):
        if cond():
            return True
        threading.Event().wait(0.01)
    return False


def seed(store, n):
    store.upsert_clips("1", [mk(i) for i in range(n)])


ARGS = (Streamer, date(2026, 1, 1), date(2026, 1, 31))


def test_cached_first_returns_immediately_and_refreshes_in_background(store):
    seed(store, 5)
    gate = threading.Event()
    fake = FakeTwitch([mk(100)], gate=gate)
    live = live_for(store, fake)
    assert live.ensure_cached_first(*ARGS, 5, TODAY, 5) is False
    assert wait_for(lambda: fake.calls)
    assert store.top_clips("1", None, None, 10, 0)[1] == 5
    gate.set()
    assert wait_for(lambda: store.top_clips("1", None, None, 10, 0)[1] == 6)


def test_cached_first_does_not_duplicate_inflight_refresh(store):
    seed(store, 5)
    gate = threading.Event()
    fake = FakeTwitch([mk(100)], gate=gate)
    live = live_for(store, fake)
    live.ensure_cached_first(*ARGS, 5, TODAY, 5)
    assert wait_for(lambda: fake.calls)
    live.ensure_cached_first(*ARGS, 5, TODAY, 5)
    live.ensure_cached_first(*ARGS, 5, TODAY, 5)
    gate.set()
    assert wait_for(lambda: not live._inflight)
    assert len(fake.calls) == 1


def test_cached_first_swallows_background_errors(store):
    seed(store, 5)
    fake = FakeTwitch(error=TwitchError("boom"))
    live = live_for(store, fake)
    assert live.ensure_cached_first(*ARGS, 5, TODAY, 5) is False
    assert wait_for(lambda: fake.calls and not live._inflight)


def test_cached_first_blocks_when_cache_is_short(store):
    seed(store, 2)
    fake = FakeTwitch([mk(100)])
    live = live_for(store, fake)
    assert live.ensure_cached_first(*ARGS, 5, TODAY, 2) is False
    assert len(fake.calls) == 1
    assert store.top_clips("1", None, None, 10, 0)[1] == 3


def test_cached_first_exact_range_unchanged(store):
    store.add_windows("1", [(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))])
    store.mark_done("1", datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC),
                    datetime(2026, 3, 1, tzinfo=UTC), False)
    seed(store, 5)
    fake = FakeTwitch([mk(100)])
    assert live_for(store, fake).ensure_cached_first(*ARGS, 5, TODAY, 5) is True
    assert fake.calls == []
