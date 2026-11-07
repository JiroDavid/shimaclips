import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from store import Store, Streamer
from twitch import TwitchClient

MAX_LIVE = 1000


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


class LiveClips:
    def __init__(self, store: Store, twitch_factory: Callable[[], TwitchClient],
                 ttl: float = 120.0, clock: Callable[[], float] = time.monotonic):
        self._store = store
        self._twitch_factory = twitch_factory
        self._ttl = ttl
        self._clock = clock
        self._memo: dict[tuple, tuple[int, float]] = {}
        self._locks: dict[tuple, threading.Lock] = {}
        self._master = threading.Lock()

    def _fresh(self, key: tuple, need: int) -> bool:
        entry = self._memo.get(key)
        return entry is not None and entry[0] >= need and self._clock() - entry[1] < self._ttl

    def ensure(self, streamer: Streamer, start: date | None, end: date | None,
               need: int, today: date) -> bool:
        bid = streamer.broadcaster_id
        if self._store.range_exact(bid, start, end, streamer.account_created.date(), today):
            return True
        need = min(need, MAX_LIVE)
        key = (bid, start, end)
        with self._master:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            if self._fresh(key, need):
                return False
            start_dt = _midnight(start) if start is not None else None
            end_dt = _midnight(end + timedelta(days=1)) if end is not None else None
            clips = self._twitch_factory().fetch_top(bid, start_dt, end_dt, need)
            self._store.upsert_clips(bid, clips)
            self._memo[key] = (need, self._clock())
        return False
