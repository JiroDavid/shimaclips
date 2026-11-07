import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable

from fetcher import plan_windows, run_fetch
from store import Store, Streamer
from twitch import TwitchClient, TwitchError

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

    def ensure(self, login: str, mode: str = "auto") -> tuple[Streamer, LoadState]:
        login = normalize_login(login)
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
                self._jobs[user.id] = job
                self._pool.submit(self._run, job, twitch, user.id)
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

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)

    def _snapshot(self, broadcaster_id: str, job: _Job) -> LoadState:
        with self._lock:
            status, error, started_at = job.status, job.error, job.started_at
        p = self.store.progress(broadcaster_id)
        return LoadState(status, error, p.windows_done, p.windows_total, p.clips, p.capped, started_at)

    def _finish(self, job: _Job, status: str, error: str | None) -> None:
        with self._lock:
            job.status = status
            job.error = error

    def _run(self, job: _Job, twitch, broadcaster_id: str) -> None:
        self._finish(job, "running", None)
        try:
            run_fetch(self.store, twitch, broadcaster_id)
        except TwitchError as e:
            self._finish(job, "error", str(e) or "Twitch request failed")
        except Exception:
            self._finish(job, "error", "Unexpected error while loading clips")
        else:
            self._finish(job, "done", None)
