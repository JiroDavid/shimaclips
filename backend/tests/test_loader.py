import threading
import time
from datetime import datetime, timezone

import pytest

from loader import LoadManager, StreamerNotFound, normalize_login, state_to_dict
from store import Store
from twitch import ClipsResult, TwitchError, User

UTC = timezone.utc
CREATED = datetime(2026, 10, 1, tzinfo=UTC)


def wait_for(cond, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


class FakeTwitch:
    def __init__(self, logins):
        self.users = {l: User(str(i + 1), l, l.title(), CREATED) for i, l in enumerate(logins)}
        self.gates = {}
        self.entered = {}
        self.fail = {}
        self.calls = {}
        self.lock = threading.Lock()

    def get_user(self, login):
        return self.users.get(login)

    def hold(self, login):
        uid = self.users[login].id
        self.gates[uid] = threading.Event()
        self.entered[uid] = threading.Event()

    def release(self, login):
        self.gates[self.users[login].id].set()

    def fetch_window(self, broadcaster_id, start, end):
        with self.lock:
            self.calls[broadcaster_id] = self.calls.get(broadcaster_id, 0) + 1
            n = self.calls[broadcaster_id]
        if broadcaster_id in self.entered:
            self.entered[broadcaster_id].set()
            self.gates[broadcaster_id].wait(5)
        if self.fail.get(broadcaster_id) == n:
            raise TwitchError("rate limited")
        return ClipsResult([], False)


@pytest.fixture
def env(tmp_path):
    twitch = FakeTwitch(["alpha", "beta", "gamma"])
    store = Store(tmp_path / "s.db")
    mgr = LoadManager(store, lambda: twitch, max_concurrent=2)
    yield twitch, store, mgr
    for g in twitch.gates.values():
        g.set()
    mgr.shutdown()


def test_normalize_login_cases():
    assert normalize_login(" @Shroud ") == "shroud"
    for bad in ["a/b", "", "   ", "@", "a" * 26]:
        with pytest.raises(ValueError):
            normalize_login(bad)
    assert normalize_login("a" * 25) == "a" * 25


def test_ensure_twice_returns_same_running_job(env):
    twitch, store, mgr = env
    twitch.hold("alpha")
    s1, st1 = mgr.ensure("alpha")
    assert twitch.entered[s1.broadcaster_id].wait(5)
    s2, st2 = mgr.ensure("Alpha")
    assert s1.broadcaster_id == s2.broadcaster_id
    assert st1.started_at == st2.started_at
    assert st2.status == "running"
    twitch.release("alpha")
    assert wait_for(lambda: mgr.state("alpha").status == "done")
    assert twitch.calls[s1.broadcaster_id] == 2


def test_unknown_streamer_raises_not_found(env):
    _, _, mgr = env
    with pytest.raises(StreamerNotFound):
        mgr.ensure("nobody")
    assert mgr.state("nobody") is None


def test_third_job_is_queued_when_limit_is_two(env):
    twitch, _, mgr = env
    for n in ("alpha", "beta", "gamma"):
        twitch.hold(n)
    mgr.ensure("alpha")
    mgr.ensure("beta")
    assert twitch.entered["1"].wait(5) and twitch.entered["2"].wait(5)
    _, st = mgr.ensure("gamma")
    assert st.status == "queued"
    assert mgr.state("gamma").status == "queued"
    twitch.release("alpha")
    assert twitch.entered["3"].wait(5)
    assert mgr.state("gamma").status == "running"
    twitch.release("beta")
    twitch.release("gamma")
    assert wait_for(lambda: mgr.state("gamma").status == "done")


def test_twitch_error_sets_error_state_and_keeps_done_windows(env):
    twitch, store, mgr = env
    twitch.fail["1"] = 2
    mgr.ensure("alpha")
    assert wait_for(lambda: mgr.state("alpha").status == "error")
    st = mgr.state("alpha")
    assert st.error == "rate limited"
    assert st.windows_done == 1
    assert st.windows_total == 2


def test_job_continues_when_another_streamer_is_opened(env):
    twitch, _, mgr = env
    twitch.hold("alpha")
    mgr.ensure("alpha")
    assert twitch.entered["1"].wait(5)
    mgr.ensure("beta")
    assert mgr.state("alpha").status == "running"
    twitch.release("alpha")
    assert wait_for(lambda: mgr.state("alpha").status == "done")
    assert wait_for(lambda: mgr.state("beta").status == "done")


def test_ensure_after_done_starts_fresh_auto_refresh(env):
    twitch, _, mgr = env
    _, st1 = mgr.ensure("alpha")
    assert wait_for(lambda: mgr.state("alpha").status == "done")
    before = twitch.calls["1"]
    _, st2 = mgr.ensure("alpha")
    assert st2.started_at >= st1.started_at
    assert wait_for(lambda: mgr.state("alpha").status == "done" and twitch.calls["1"] > before)


def test_state_to_dict_has_all_fields(env):
    _, _, mgr = env
    mgr.ensure("alpha")
    d = state_to_dict(mgr.state("alpha"))
    assert set(d) == {"status", "error", "windows_done", "windows_total", "clips", "capped", "started_at"}
