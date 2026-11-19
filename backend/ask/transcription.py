import logging
import queue
import sqlite3
import threading
import time
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, timedelta

from ask.embed import build_vectors
from ask.keyword import add_missing
from ask.live_data import ensure_range
from ask.services import Services
from ask.subset import pick_subset
from ask.transcribe import transcribe_missing
from store import Streamer
from twitch import TwitchError

log = logging.getLogger(__name__)

ACTIVE = ("queued", "finding", "transcribing", "indexing")
DAYS = 365
PER_MONTH_NEED = 120
CAP = 1000
CHUNK = 50


@dataclass
class Job:
    state: str = "queued"
    total: int = 0
    processed: int = 0
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None


def _months(since: date, today: date):
    start = date(since.year, since.month, 1)
    while start <= today:
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        yield start, end
        start = end


class TranscriptionManager:
    def __init__(self, svc: Services):
        self.svc = svc
        self._jobs: dict[str, Job] = {}
        self._queue: queue.Queue[Streamer] = queue.Queue()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _transcribed(self, bid: str) -> int:
        with closing(sqlite3.connect(self.svc.db_path, timeout=30)) as conn:
            try:
                return conn.execute(
                    "SELECT COUNT(*) FROM transcripts t JOIN clips k ON k.id = t.clip_id WHERE k.broadcaster_id = ?", (bid,)
                ).fetchone()[0]
            except sqlite3.OperationalError:
                return 0

    def status(self, streamer: Streamer) -> dict:
        job = self._jobs.get(streamer.broadcaster_id)
        transcribed = self._transcribed(streamer.broadcaster_id)
        if job is None:
            state = "done" if transcribed > 0 else "idle"
            return {"login": streamer.login, "display_name": streamer.display_name, "state": state,
                    "total": transcribed, "processed": transcribed, "transcribed": transcribed, "error": None}
        return {"login": streamer.login, "display_name": streamer.display_name, "state": job.state,
                "total": job.total, "processed": job.processed, "transcribed": transcribed, "error": job.error}

    def start(self, streamer: Streamer) -> dict:
        with self._lock:
            job = self._jobs.get(streamer.broadcaster_id)
            if job is None or job.state == "error":
                self._jobs[streamer.broadcaster_id] = Job()
                self._queue.put(streamer)
                if self._thread is None or not self._thread.is_alive():
                    self._stop.clear()
                    self._thread = threading.Thread(target=self._worker, name="transcriber", daemon=True)
                    self._thread.start()
        return self.status(streamer)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                streamer = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            job = self._jobs[streamer.broadcaster_id]
            try:
                self._run(streamer, job)
            except Exception as e:
                log.warning("Transcription of '%s' failed", streamer.login, exc_info=True)
                job.state, job.error = "error", str(e) or type(e).__name__
            job.finished_at = time.time()

    def _run(self, streamer: Streamer, job: Job) -> None:
        today = date.today()
        since = today - timedelta(days=DAYS)
        job.state = "finding"
        failures = 0
        for start, end in _months(since, today):
            if self._stop.is_set():
                return
            try:
                ensure_range(self.svc, streamer, start, end, PER_MONTH_NEED, today)
            except TwitchError:
                failures += 1
        with closing(sqlite3.connect(self.svc.db_path, timeout=120)) as conn:
            planned = pick_subset(conn, streamer.login, since.isoformat(), 60, 10, 2, CAP)
            if not planned:
                job.state, job.error = "error", "No clips were found for this streamer in the last year."
                if failures:
                    job.error = "Twitch did not return this streamer's clips. Try again in a moment."
                return
            done = {r[0] for r in conn.execute("SELECT clip_id FROM transcripts")} if self._has_table(conn) else set()
            todo = [c for c in planned if c[0] not in done]
            job.total, job.processed = len(planned), len(planned) - len(todo)
            job.state = "transcribing"
            for i in range(0, len(todo), CHUNK):
                if self._stop.is_set():
                    return
                transcribe_missing(
                    conn, todo[i:i + CHUNK],
                    on_clip=lambda: setattr(job, "processed", job.processed + 1),
                    should_stop=self._stop.is_set,
                )
                job.state = "indexing"
                build_vectors(conn)
                add_missing(conn)
                job.state = "transcribing"
            job.processed = job.total
        job.state = "done"

    @staticmethod
    def _has_table(conn: sqlite3.Connection) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'transcripts'").fetchone() is not None
