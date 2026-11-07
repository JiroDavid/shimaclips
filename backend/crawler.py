import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from fetcher import plan_windows, run_fetch
from loader import LoadManager
from store import Store, WatchEntry
from twitch import TwitchClient, TwitchError, User

log = logging.getLogger(__name__)


class _SetupFailed(Exception):
    pass


class WatchCrawler:
    def __init__(self, store: Store, manager: LoadManager, twitch_factory: Callable[[], TwitchClient],
                 interval: float = 5.0, refresh_after: timedelta = timedelta(hours=24),
                 window_delay: float = 0.25, retry_after: float = 60.0,
                 now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
                 monotonic: Callable[[], float] = time.monotonic):
        self.store = store
        self.manager = manager
        self.twitch_factory = twitch_factory
        self.interval = interval
        self.refresh_after = refresh_after
        self.window_delay = window_delay
        self.retry_after = retry_after
        self.now = now
        self.monotonic = monotonic
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._working: str | None = None
        self._errors: dict[str, float] = {}
        self._setup_failed_at: float | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="watch-crawler", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        with self._lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)

    def _loop(self) -> None:
        while not self._stopped.wait(self.interval):
            try:
                self.tick()
            except Exception:
                log.exception("Watchlist crawler pass failed")

    def _should_stop(self) -> bool:
        return self._stopped.is_set() or self.manager.interactive_active()

    def _twitch(self) -> TwitchClient:
        try:
            twitch = self.twitch_factory()
        except Exception as e:
            self._setup_failed_at = self.monotonic()
            log.warning("Watchlist crawler cannot reach Twitch: %s", str(e) or type(e).__name__)
            raise _SetupFailed() from e
        self._setup_failed_at = None
        return twitch

    def _eligible(self, entry: WatchEntry) -> bool:
        return not entry.paused and not self._backing_off(entry.login)

    def _needs_coarse(self, entry: WatchEntry) -> bool:
        if entry.broadcaster_id is None:
            return True
        if self._user(entry) is None:
            return False
        bid = entry.broadcaster_id
        return (self.store.progress(bid).windows_total == 0
                or self.store.next_pending(bid, None, coarse_only=True) is not None)

    def _run_should_stop(self, login: str, coarse_only: bool) -> Callable[[], bool]:
        def should_stop() -> bool:
            if self._should_stop():
                return True
            entries = self.store.watch_list()
            mine = next((e for e in entries if e.login == login), None)
            if mine is None or mine.paused:
                return True
            if coarse_only:
                return False
            return any(e.login != login and self._eligible(e) and self._needs_coarse(e) for e in entries)
        return should_stop

    def _allowed(self, bid: str) -> set[int]:
        return self.store.exact_years(bid, self.now().year)

    def _record_error(self, login: str) -> None:
        with self._lock:
            self._errors[login] = self.monotonic()

    def _backing_off(self, login: str) -> bool:
        with self._lock:
            at = self._errors.get(login)
        return at is not None and self.monotonic() - at < self.retry_after

    def _stale(self, entry: WatchEntry) -> bool:
        return entry.last_refreshed is None or self.now() - entry.last_refreshed >= self.refresh_after

    def _resolve(self, entries: list[WatchEntry]) -> None:
        for e in entries:
            if e.broadcaster_id is not None or e.paused or self._backing_off(e.login):
                continue
            if self._should_stop():
                return
            twitch = self._twitch()
            try:
                user = twitch.get_user(e.login)
            except TwitchError as err:
                log.warning("Could not look up watchlist streamer '%s': %s", e.login, err)
                self._record_error(e.login)
                continue
            except Exception:
                log.warning("Could not look up watchlist streamer '%s'", e.login, exc_info=True)
                self._record_error(e.login)
                continue
            if user is None:
                log.warning("Watchlist streamer '%s' does not exist on Twitch; removing it", e.login)
                self.store.watch_remove(e.login)
                continue
            self.store.upsert_streamer(user)
            self.store.watch_set_broadcaster(e.login, user.id)
            with self._lock:
                self._errors.pop(e.login, None)

    def _user(self, entry: WatchEntry) -> User | None:
        s = self.store.get_streamer(entry.login)
        if s is None or s.broadcaster_id != entry.broadcaster_id:
            return None
        return User(s.broadcaster_id, s.login, s.display_name, s.account_created)

    def _run(self, login: str, bid: str, coarse_only: bool) -> bool:
        twitch = self._twitch()
        with self._lock:
            self._working = login
        try:
            run_fetch(self.store, twitch, bid, now=self.now,
                      should_stop=self._run_should_stop(login, coarse_only),
                      allowed_years=lambda: self._allowed(bid),
                      coarse_only=coarse_only, delay=self.window_delay)
        except TwitchError as err:
            log.warning("Background load of '%s' failed: %s", login, err)
            self._record_error(login)
            return False
        except Exception:
            log.warning("Background load of '%s' failed", login, exc_info=True)
            self._record_error(login)
            return False
        finally:
            with self._lock:
                self._working = None
        with self._lock:
            self._errors.pop(login, None)
        return True

    def _refine(self, login: str, bid: str) -> None:
        if not self._run(login, bid, coarse_only=False):
            return
        if not self._stopped.is_set() and self.store.next_pending(bid, self._allowed(bid)) is None:
            self.store.watch_mark_refreshed(login, self.now())

    def tick(self) -> None:
        if self._should_stop():
            return
        failed = self._setup_failed_at
        if failed is not None and self.monotonic() - failed < self.retry_after:
            return
        try:
            self._tick()
        except _SetupFailed:
            return

    def _tick(self) -> None:
        entries = self.store.watch_list()
        with self._lock:
            known = {e.login for e in entries}
            self._errors = {k: v for k, v in self._errors.items() if k in known}
        self._resolve(entries)
        entries = self.store.watch_list()
        active: list[tuple[WatchEntry, User]] = []
        for e in entries:
            if e.paused or e.broadcaster_id is None or self._backing_off(e.login):
                continue
            user = self._user(e)
            if user is not None:
                active.append((e, user))

        for e, user in active:
            if self._should_stop():
                return
            plan_windows(self.store, user, "resume", self.now())
            if self.store.next_pending(user.id, None, coarse_only=True) is not None:
                self._run(e.login, user.id, coarse_only=True)
                return

        for e, user in active:
            if self.store.next_pending(user.id, self._allowed(user.id)) is not None:
                self._refine(e.login, user.id)
                return

        for e, user in active:
            if self._should_stop():
                return
            if self._stale(e):
                if e.last_refreshed is not None:
                    plan_windows(self.store, user, "auto", self.now())
                self._refine(e.login, user.id)
                return

    def status(self, login: str) -> dict:
        login = login.lower()
        entry = next((e for e in self.store.watch_list() if e.login == login), None)
        if entry is None:
            raise KeyError(login)
        bid = entry.broadcaster_id
        if bid is not None:
            allowed = self._allowed(bid)
            p = self.store.progress(bid, allowed)
            done, total = p.windows_done, p.windows_total
        else:
            done = total = 0
        with self._lock:
            working = self._working == login
            errored = login in self._errors
        if entry.paused:
            state = "paused"
        elif working:
            state = "loading"
        elif errored:
            state = "error"
        elif bid is None or self._stale(entry) or self.store.next_pending(bid, allowed) is not None:
            state = "waiting"
        else:
            state = "up_to_date"
        return {"state": state, "windows_done": done, "windows_total": total}
