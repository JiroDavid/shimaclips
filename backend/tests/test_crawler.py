import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from crawler import WatchCrawler
from store import Store
from twitch import ClipsResult, TwitchError, User

UTC = timezone.utc
CREATED = datetime(2026, 9, 1, tzinfo=UTC)
NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)


def is_month(start, end):
    return end - start >= timedelta(days=27)


class FakeTwitch:
    def __init__(self, logins):
        self.users = {l: User(str(i + 1), l, l.title(), CREATED) for i, l in enumerate(logins)}
        self.calls = []
        self.lookups = []
        self.truncate_months = False
        self.fail = {}
        self.on_fetch = None

    def get_user(self, login):
        self.lookups.append(login)
        return self.users.get(login)

    def fetch_window(self, broadcaster_id, start, end):
        self.calls.append((broadcaster_id, start, end))
        if self.on_fetch:
            self.on_fetch(broadcaster_id, start, end)
        if self.fail.get(broadcaster_id):
            self.fail[broadcaster_id] -= 1
            raise TwitchError("rate limited")
        return ClipsResult([], self.truncate_months and is_month(start, end))


class FakeManager:
    def __init__(self):
        self.active = False

    def interactive_active(self):
        return self.active


class Clock:
    def __init__(self):
        self.now = NOW
        self.mono = 1000.0


@pytest.fixture
def env(tmp_path):
    twitch = FakeTwitch(["alpha", "beta", "gamma"])
    store = Store(tmp_path / "c.db")
    mgr = FakeManager()
    clock = Clock()
    crawler = WatchCrawler(store, mgr, lambda: twitch, window_delay=0, retry_after=60,
                           now=lambda: clock.now, monotonic=lambda: clock.mono)
    yield twitch, store, mgr, clock, crawler
    crawler.stop()


def watch(store, twitch, *logins):
    for l in logins:
        store.upsert_streamer(twitch.users[l])
        store.watch_add(l, twitch.users[l].id)


def entry(store, login):
    return next(e for e in store.watch_list() if e.login == login)


def bid_of(twitch, login):
    return twitch.users[login].id


def run_until_idle(crawler, twitch, limit=20):
    for _ in range(limit):
        before = len(twitch.calls)
        crawler.tick()
        if len(twitch.calls) == before:
            return
    raise AssertionError("crawler never went idle")


def test_tick_does_nothing_while_interactive_job_active(env):
    twitch, store, mgr, _, crawler = env
    watch(store, twitch, "alpha")
    store.watch_add("beta", None)
    mgr.active = True
    crawler.tick()
    assert twitch.calls == [] and twitch.lookups == []
    assert entry(store, "beta").broadcaster_id is None


def test_coarse_pass_runs_for_all_entries_before_any_refinement(env):
    twitch, store, _, _, crawler = env
    twitch.truncate_months = True
    watch(store, twitch, "alpha", "beta")
    crawler.tick()
    assert {c[0] for c in twitch.calls} == {"1"}
    assert all(is_month(s, e) for _, s, e in twitch.calls)
    assert len(twitch.calls) == 3
    crawler.tick()
    assert len(twitch.calls) == 6
    assert all(is_month(s, e) for _, s, e in twitch.calls)
    assert {c[0] for c in twitch.calls[3:]} == {"2"}
    crawler.tick()
    assert len(twitch.calls) > 6
    assert not any(is_month(s, e) for _, s, e in twitch.calls[6:])


def test_only_one_entry_refines_at_a_time(env):
    twitch, store, _, _, crawler = env
    twitch.truncate_months = True
    watch(store, twitch, "alpha", "beta")
    crawler.tick()
    crawler.tick()
    n = len(twitch.calls)
    crawler.tick()
    assert {c[0] for c in twitch.calls[n:]} == {"1"}
    assert store.next_pending("1", store.exact_years("1", NOW.year)) is None
    assert store.next_pending("2", store.exact_years("2", NOW.year)) is not None
    assert entry(store, "alpha").last_refreshed == NOW
    assert entry(store, "beta").last_refreshed is None
    n = len(twitch.calls)
    crawler.tick()
    assert {c[0] for c in twitch.calls[n:]} == {"2"}
    assert entry(store, "beta").last_refreshed == NOW


def test_unknown_seeded_login_is_removed_with_warning(env, caplog):
    twitch, store, _, _, crawler = env
    store.watch_add("ghost", None)
    store.watch_add("alpha", None)
    with caplog.at_level(logging.WARNING):
        crawler.tick()
    logins = [e.login for e in store.watch_list()]
    assert logins == ["alpha"]
    assert any("ghost" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)
    assert entry(store, "alpha").broadcaster_id == "1"
    assert store.get_streamer("alpha").display_name == "Alpha"
    assert {c[0] for c in twitch.calls} == {"1"}


def test_paused_entry_is_skipped(env):
    twitch, store, _, _, crawler = env
    watch(store, twitch, "alpha")
    store.watch_set_paused("alpha", True)
    crawler.tick()
    assert twitch.calls == []
    assert crawler.status("alpha")["state"] == "paused"


def test_stale_entry_is_refreshed_and_marked(env):
    twitch, store, _, clock, crawler = env
    watch(store, twitch, "alpha")
    run_until_idle(crawler, twitch)
    assert entry(store, "alpha").last_refreshed == NOW
    clock.now = NOW + timedelta(hours=25)
    n = len(twitch.calls)
    crawler.tick()
    refetched = [(s, e) for _, s, e in twitch.calls[n:]]
    assert (datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)) in refetched
    assert entry(store, "alpha").last_refreshed == clock.now
    assert crawler.status("alpha")["state"] == "up_to_date"


def test_up_to_date_entry_is_left_alone(env):
    twitch, store, _, clock, crawler = env
    watch(store, twitch, "alpha")
    run_until_idle(crawler, twitch)
    clock.now = NOW + timedelta(hours=1)
    n = len(twitch.calls)
    crawler.tick()
    assert len(twitch.calls) == n
    assert entry(store, "alpha").last_refreshed == NOW
    st = crawler.status("alpha")
    assert st["state"] == "up_to_date"
    assert st["windows_done"] == st["windows_total"] == 3


def test_interactive_job_started_mid_run_stops_background_after_current_window(env):
    twitch, store, mgr, _, crawler = env
    watch(store, twitch, "alpha")

    def start_interactive(*_):
        mgr.active = True

    twitch.on_fetch = start_interactive
    crawler.tick()
    assert len(twitch.calls) == 1
    assert store.next_pending("1", coarse_only=True) is not None
    assert entry(store, "alpha").last_refreshed is None
    assert crawler.status("alpha")["state"] == "waiting"
    twitch.on_fetch = None
    crawler.tick()
    assert len(twitch.calls) == 1
    mgr.active = False
    run_until_idle(crawler, twitch)
    assert len(twitch.calls) == 3
    assert entry(store, "alpha").last_refreshed == NOW


def test_stop_returns_promptly_and_keeps_windows_pending(tmp_path):
    twitch = FakeTwitch(["alpha"])
    store = Store(tmp_path / "c.db")
    watch(store, twitch, "alpha")
    entered, gate = threading.Event(), threading.Event()

    def block(*_):
        entered.set()
        gate.wait(5)

    twitch.on_fetch = block
    crawler = WatchCrawler(store, FakeManager(), lambda: twitch, interval=0.01,
                           window_delay=0, now=lambda: NOW)
    crawler.start()
    assert entered.wait(5)
    stopper = threading.Thread(target=crawler.stop)
    t0 = time.monotonic()
    stopper.start()
    assert crawler._stopped.wait(5)
    gate.set()
    stopper.join(5)
    assert not stopper.is_alive()
    assert time.monotonic() - t0 < 2
    assert not crawler._thread.is_alive()
    assert len(twitch.calls) == 1
    assert store.next_pending("1", coarse_only=True) is not None
    assert entry(store, "alpha").last_refreshed is None
    crawler.tick()
    assert len(twitch.calls) == 1


def test_twitch_error_marks_entry_error_and_continues_with_others(env, caplog):
    twitch, store, _, _, crawler = env
    watch(store, twitch, "alpha", "beta")
    twitch.fail["1"] = 1
    with caplog.at_level(logging.WARNING):
        crawler.tick()
    assert crawler.status("alpha")["state"] == "error"
    assert any("alpha" in r.getMessage() for r in caplog.records)
    n = len(twitch.calls)
    crawler.tick()
    assert {c[0] for c in twitch.calls[n:]} == {"2"}
    run_until_idle(crawler, twitch)
    assert entry(store, "beta").last_refreshed == NOW
    assert entry(store, "alpha").last_refreshed is None
    assert crawler.status("alpha")["state"] == "error"


def test_error_entry_retried_after_backoff(env):
    twitch, store, _, clock, crawler = env
    watch(store, twitch, "alpha")
    twitch.fail["1"] = 1
    crawler.tick()
    assert crawler.status("alpha")["state"] == "error"
    n = len(twitch.calls)
    clock.mono += 59
    crawler.tick()
    assert len(twitch.calls) == n
    clock.mono += 2
    run_until_idle(crawler, twitch)
    assert len(twitch.calls) > n
    assert entry(store, "alpha").last_refreshed == NOW
    assert crawler.status("alpha")["state"] == "up_to_date"


def test_unresolvable_lookup_error_is_recorded_and_others_continue(env):
    twitch, store, _, _, crawler = env
    watch(store, twitch, "beta")
    store.watch_add("alpha", None)

    def boom(login):
        raise TwitchError("down")

    twitch.get_user = boom
    crawler.tick()
    assert crawler.status("alpha")["state"] == "error"
    assert entry(store, "alpha").broadcaster_id is None
    assert {c[0] for c in twitch.calls} == {"2"}


def test_status_reports_loading_for_entry_being_crawled(env):
    twitch, store, _, _, crawler = env
    watch(store, twitch, "alpha", "beta")
    seen = []
    twitch.on_fetch = lambda bid, *_: seen.append((bid, crawler.status("alpha"), crawler.status("beta")))
    crawler.tick()
    assert seen
    for bid, a, b in seen:
        assert bid == "1"
        assert a["state"] == "loading" and a["windows_total"] == 3
        assert b["state"] == "waiting"
    assert crawler.status("alpha")["state"] == "waiting"


def test_status_unknown_login_raises(env):
    _, _, _, _, crawler = env
    with pytest.raises(KeyError):
        crawler.status("nobody")


def test_status_for_unresolved_entry_is_waiting_with_zero_progress(env):
    _, store, _, _, crawler = env
    store.watch_add("alpha", None)
    assert crawler.status("alpha") == {"state": "waiting", "windows_done": 0, "windows_total": 0}
