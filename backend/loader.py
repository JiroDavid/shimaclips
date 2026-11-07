import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

from fetcher import plan_windows, run_fetch
from store import Store, Streamer
from twitch import TwitchClient, TwitchError, User

_LOGIN = re.compile(r"^[a-z0-9_]{1,25}$")


def normalize_login(raw: str) -> str:
    login = raw.strip()
    if login.startswith("@"):
        login = login[1:]
    login = login.lower()
    if not _LOGIN.match(login):
        raise ValueError(f"invalid streamer login: {raw!r}")
    return login


class StreamerNotFound(Exception):
    pass


class LoaderUnavailable(Exception):
    pass


STOPPED = "Loading stopped because the server is shutting down"


@dataclass
class LoadState:
    status: str
    error: str | None
    windows_done: int
    windows_total: int
    clips: int
    capped: int
    started_at: float


def state_to_dict(state: LoadState) -> dict:
    return asdict(state)


@dataclass
class _Job:
    status: str
    error: str | None
    started_at: float


class LoadManager:
    def __init__(self, store: Store, twitch_factory: Callable[[], TwitchClient],
                 max_concurrent: int = 2):
        self.store = store
        self.twitch_factory = twitch_factory
        self._pool = ThreadPoolExecutor(max_workers=max_concurrent)
        self._lock = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._stop = threading.Event()

    def ensure(self, login: str, mode: str = "auto") -> tuple[Streamer, LoadState]:
        login = normalize_login(login)
        if self._stop.is_set():
            raise LoaderUnavailable()
        twitch = self.twitch_factory()
        user = twitch.get_user(login)
        if user is None:
            raise StreamerNotFound(login)
        self.store.upsert_streamer(user)
        streamer = self.store.get_streamer(login)
        with self._lock:
            job = self._jobs.get(user.id)
            if job is None or job.status not in ("queued", "running"):
                plan_windows(self.store, user, mode, datetime.now(timezone.utc))
                job = _Job("queued", None, time.time())
                try:
                    self._pool.submit(self._run, job, twitch, user.id)
                except RuntimeError:
                    raise LoaderUnavailable()
                self._jobs[user.id] = job
        return streamer, self._snapshot(user.id, job)

    def state(self, login: str) -> LoadState | None:
        try:
            login = normalize_login(login)
        except ValueError:
            return None
        streamer = self.store.get_streamer(login)
        if streamer is None:
            return None
        with self._lock:
            job = self._jobs.get(streamer.broadcaster_id)
        if job is None:
            return None
        return self._snapshot(streamer.broadcaster_id, job)

    def interactive_active(self) -> bool:
        with self._lock:
            return any(j.status in ("queued", "running") for j in self._jobs.values())

    def shutdown(self, wait: bool = False) -> None:
        self._stop.set()
        self._pool.shutdown(wait=wait, cancel_futures=True)
        with self._lock:
            for job in self._jobs.values():
                if job.status == "queued":
                    job.status, job.error = "error", STOPPED

    def _exact_years(self, broadcaster_id: str) -> set[int]:
        return self.store.exact_years(broadcaster_id, datetime.now(timezone.utc).year)

    def set_year(self, login: str, year: int, enabled: bool) -> None:
        login = normalize_login(login)
        if self._stop.is_set():
            raise LoaderUnavailable()
        streamer = self.store.get_streamer(login)
        if streamer is None:
            raise StreamerNotFound(login)
        bid = streamer.broadcaster_id
        self.store.set_exact_year(bid, year, enabled)
        if not enabled:
            return
        with self._lock:
            job = self._jobs.get(bid)
            if job is not None and job.status in ("queued", "running"):
                return
            twitch = self.twitch_factory()
            user = User(bid, streamer.login, streamer.display_name, streamer.account_created)
            plan_windows(self.store, user, "resume", datetime.now(timezone.utc))
            job = _Job("queued", None, time.time())
            try:
                self._pool.submit(self._run, job, twitch, bid)
            except RuntimeError:
                raise LoaderUnavailable()
            self._jobs[bid] = job

    def _snapshot(self, broadcaster_id: str, job: _Job) -> LoadState:
        with self._lock:
            status, error, started_at = job.status, job.error, job.started_at
        p = self.store.progress(broadcaster_id, self._exact_years(broadcaster_id))
        return LoadState(status, error, p.windows_done, p.windows_total, p.clips, p.capped, started_at)

    def _finish(self, job: _Job, status: str, error: str | None) -> None:
        with self._lock:
            job.status = status
            job.error = error

    def _run(self, job: _Job, twitch, broadcaster_id: str) -> None:
        self._finish(job, "running", None)
        try:
            run_fetch(self.store, twitch, broadcaster_id, should_stop=self._stop.is_set,
                      allowed_years=lambda: self._exact_years(broadcaster_id))
        except TwitchError as e:
            self._finish(job, "error", str(e) or "Twitch request failed")
        except Exception:
            self._finish(job, "error", "Unexpected error while loading clips")
        else:
            if self._stop.is_set():
                self._finish(job, "error", STOPPED)
            else:
                self._finish(job, "done", None)
