import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from twitch import Clip, User

_FMT = "%Y-%m-%dT%H:%M:%SZ"
SCHEMA_VERSION = 3


def _enc(d: datetime) -> str:
    return d.astimezone(timezone.utc).strftime(_FMT)


def _dec(s: str) -> datetime:
    return datetime.strptime(s, _FMT).replace(tzinfo=timezone.utc)


def _day_start(d: date) -> str:
    return f"{d.isoformat()}T00:00:00Z"


@dataclass
class Window:
    start: datetime
    end: datetime
    status: str
    fetched_at: datetime | None
    truncated: bool


@dataclass
class Streamer:
    broadcaster_id: str
    login: str
    display_name: str
    account_created: datetime


@dataclass
class Bucket:
    key: str
    count: int
    ready: bool
    state: str


@dataclass
class YearInfo:
    year: int
    enabled: bool
    state: str
    clips: int


@dataclass
class Progress:
    windows_done: int
    windows_total: int
    clips: int
    capped: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS streamers (
    broadcaster_id TEXT PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    account_created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    broadcaster_id TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    thumbnail_url TEXT NOT NULL,
    view_count INTEGER NOT NULL,
    duration REAL NOT NULL,
    creator_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS clips_by_created ON clips (broadcaster_id, created_at);
CREATE INDEX IF NOT EXISTS clips_by_views ON clips (broadcaster_id, view_count);
CREATE TABLE IF NOT EXISTS windows (
    broadcaster_id TEXT NOT NULL,
    start TEXT NOT NULL,
    "end" TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    fetched_at TEXT,
    truncated INTEGER NOT NULL DEFAULT 0,
    has_data INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (broadcaster_id, start, "end")
);
CREATE TABLE IF NOT EXISTS streamer_years (
    broadcaster_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    enabled INTEGER NOT NULL,
    PRIMARY KEY (broadcaster_id, year)
);
"""

_MONTH_SIZED = 'julianday("end") - julianday(start) >= 27'


def _in_scope(allowed_years: set[int] | None) -> tuple[str, list]:
    if allowed_years is None:
        return "1", []
    marks = ", ".join("?" for _ in allowed_years)
    return f"({_MONTH_SIZED} OR CAST(substr(start, 1, 4) AS INTEGER) IN ({marks}))", sorted(allowed_years)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            existing = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='windows'"
            ).fetchone() is not None
            conn.executescript(_SCHEMA)
            with conn:
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version < SCHEMA_VERSION:
                    if existing and version < 2:
                        self._migrate(conn)
                    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(windows)")}
        if "has_data" not in columns:
            conn.execute("ALTER TABLE windows ADD COLUMN has_data INTEGER NOT NULL DEFAULT 0")
        # Windows fetched before the 800-clip threshold may be silently truncated, so refetch them all.
        conn.execute(
            "UPDATE windows SET status='pending', fetched_at=NULL, truncated=0, has_data=0 "
            "WHERE status='done'"
        )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _write(self, sql: str, rows: list[tuple]) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.executemany(sql, rows)

    def upsert_streamer(self, user: User) -> None:
        self._write(
            "INSERT INTO streamers (broadcaster_id, login, display_name, account_created) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(broadcaster_id) DO UPDATE SET "
            "login=excluded.login, display_name=excluded.display_name, "
            "account_created=excluded.account_created",
            [(user.id, user.login, user.display_name, _enc(user.created_at))],
        )

    def get_streamer(self, login: str) -> Streamer | None:
        with closing(self._connect()) as conn:
            r = conn.execute(
                "SELECT * FROM streamers WHERE login = ? COLLATE NOCASE", (login,)
            ).fetchone()
        if r is None:
            return None
        return Streamer(r["broadcaster_id"], r["login"], r["display_name"], _dec(r["account_created"]))

    def upsert_clips(self, broadcaster_id: str, clips: list[Clip]) -> None:
        self._write(
            "INSERT INTO clips (id, broadcaster_id, url, title, thumbnail_url, view_count, "
            "duration, creator_name, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET url=excluded.url, title=excluded.title, "
            "thumbnail_url=excluded.thumbnail_url, view_count=excluded.view_count, "
            "duration=excluded.duration, creator_name=excluded.creator_name, "
            "created_at=excluded.created_at",
            [
                (c.id, broadcaster_id, c.url, c.title, c.thumbnail_url, c.view_count,
                 c.duration, c.creator_name, c.created_at)
                for c in clips
            ],
        )

    def add_windows(self, broadcaster_id: str, windows: list[tuple[datetime, datetime]]) -> None:
        self._write(
            'INSERT OR IGNORE INTO windows (broadcaster_id, start, "end") VALUES (?, ?, ?)',
            [(broadcaster_id, _enc(s), _enc(e)) for s, e in windows],
        )

    @staticmethod
    def _window(r: sqlite3.Row) -> Window:
        return Window(
            _dec(r["start"]),
            _dec(r["end"]),
            r["status"],
            _dec(r["fetched_at"]) if r["fetched_at"] else None,
            bool(r["truncated"]),
        )

    def next_pending(self, broadcaster_id: str, allowed_years: set[int] | None = None,
                     coarse_only: bool = False) -> Window | None:
        sql = "SELECT * FROM windows WHERE broadcaster_id = ? AND status = 'pending'"
        args: list = [broadcaster_id]
        if coarse_only:
            sql += f" AND {_MONTH_SIZED}"
        else:
            expr, extra = _in_scope(allowed_years)
            sql += f" AND {expr}"
            args += extra
        sql += f' ORDER BY ({_MONTH_SIZED}) DESC, "end" DESC, start DESC LIMIT 1'
        with closing(self._connect()) as conn:
            r = conn.execute(sql, args).fetchone()
        return self._window(r) if r else None

    def exact_years(self, broadcaster_id: str, current_year: int) -> set[int]:
        years = {current_year, current_year - 1}
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT year, enabled FROM streamer_years WHERE broadcaster_id = ?",
                (broadcaster_id,),
            ).fetchall()
        for r in rows:
            if r["enabled"]:
                years.add(r["year"])
            else:
                years.discard(r["year"])
        return years

    def set_exact_year(self, broadcaster_id: str, year: int, enabled: bool) -> None:
        self._write(
            "INSERT INTO streamer_years (broadcaster_id, year, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(broadcaster_id, year) DO UPDATE SET enabled=excluded.enabled",
            [(broadcaster_id, year, int(enabled))],
        )

    def mark_done(self, broadcaster_id: str, start: datetime, end: datetime,
                  fetched_at: datetime, truncated: bool) -> None:
        self._write(
            "UPDATE windows SET status='done', fetched_at=?, truncated=?, has_data=1 "
            'WHERE broadcaster_id=? AND start=? AND "end"=?',
            [(_enc(fetched_at), int(truncated), broadcaster_id, _enc(start), _enc(end))],
        )

    def mark_split(self, broadcaster_id: str, start: datetime, end: datetime,
                   children: list[tuple[datetime, datetime]]) -> None:
        with closing(self._connect()) as conn:
            with conn:
                conn.execute(
                    "UPDATE windows SET status='split' "
                    'WHERE broadcaster_id=? AND start=? AND "end"=?',
                    (broadcaster_id, _enc(start), _enc(end)),
                )
                conn.executemany(
                    'INSERT OR IGNORE INTO windows (broadcaster_id, start, "end") VALUES (?, ?, ?)',
                    [(broadcaster_id, _enc(s), _enc(e)) for s, e in children],
                )

    def split_windows(self, broadcaster_id: str) -> list[tuple[datetime, datetime]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                'SELECT start, "end" FROM windows WHERE broadcaster_id = ? AND status = \'split\' '
                "ORDER BY start",
                (broadcaster_id,),
            ).fetchall()
        return [(_dec(r["start"]), _dec(r["end"])) for r in rows]

    def reset_windows(self, broadcaster_id: str, mode: str, now: datetime,
                      grace: timedelta) -> None:
        with closing(self._connect()) as conn:
            with conn:
                rows = conn.execute(
                    'SELECT start, "end", fetched_at FROM windows '
                    "WHERE broadcaster_id = ? AND status = 'done'",
                    (broadcaster_id,),
                ).fetchall()
                targets = []
                for r in rows:
                    if mode == "all":
                        targets.append((broadcaster_id, r["start"], r["end"]))
                    elif r["fetched_at"] is None or _dec(r["fetched_at"]) < _dec(r["end"]) + grace:
                        targets.append((broadcaster_id, r["start"], r["end"]))
                conn.executemany(
                    "UPDATE windows SET status='pending', fetched_at=NULL, truncated=0 "
                    'WHERE broadcaster_id=? AND start=? AND "end"=?',
                    targets,
                )

    def bucket_counts(self, broadcaster_id: str, start: date, end: date,
                      granularity: str) -> list[Bucket]:
        spans = _bucket_spans(start, end, granularity)
        length = 7 if granularity == "month" else 10
        with closing(self._connect()) as conn:
            counts = {
                r["k"]: r["n"]
                for r in conn.execute(
                    f"SELECT substr(created_at, 1, {length}) AS k, COUNT(*) AS n FROM clips "
                    "WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ? GROUP BY k",
                    (broadcaster_id, spans[0][1], spans[-1][2]),
                )
            } if spans else {}
            leaves = self._leaves(conn, broadcaster_id)
        out = []
        for key, b_start, b_end in spans:
            count = counts.get(key, 0)
            state = _cell_state(leaves, b_start, b_end, count)
            out.append(Bucket(key, count, state == "exact", state))
        return out

    @staticmethod
    def _leaves(conn: sqlite3.Connection, broadcaster_id: str) -> list[sqlite3.Row]:
        return conn.execute(
            'SELECT start, "end", has_data, (status = \'done\' AND truncated = 1) AS capped '
            "FROM windows WHERE broadcaster_id = ? AND status != 'split'",
            (broadcaster_id,),
        ).fetchall()

    def years_summary(self, broadcaster_id: str, first_year: int, last_year: int,
                      current_year: int) -> list[YearInfo]:
        enabled = self.exact_years(broadcaster_id, current_year)
        with closing(self._connect()) as conn:
            leaves = self._leaves(conn, broadcaster_id)
            clips = {
                int(r["y"]): r["n"]
                for r in conn.execute(
                    "SELECT substr(created_at, 1, 4) AS y, COUNT(*) AS n FROM clips "
                    "WHERE broadcaster_id = ? GROUP BY y",
                    (broadcaster_id,),
                )
            }
        out = []
        for year in range(first_year, last_year + 1):
            n = clips.get(year, 0)
            state = _cell_state(leaves, f"{year:04d}-01-01T00:00:00Z", f"{year + 1:04d}-01-01T00:00:00Z", n)
            out.append(YearInfo(year, year in enabled, state, n))
        return out

    def range_exact(self, broadcaster_id: str, start: date | None, end: date | None,
                    account_created: date, today: date) -> bool:
        lo = max(start or account_created, account_created)
        hi = min(end or today, today)
        if hi < lo:
            return True
        buckets = self.bucket_counts(broadcaster_id, lo, hi, "month")
        return all(b.state == "exact" for b in buckets)

    def top_clips(self, broadcaster_id: str, start: date | None, end: date | None,
                  limit: int, offset: int, sort: str = "views") -> tuple[list[Clip], int]:
        orders = {"views": "view_count DESC, id", "newest": "created_at DESC, id"}
        if sort not in orders:
            raise ValueError(f"Unknown sort: {sort}")
        where = "broadcaster_id = ?"
        args: list = [broadcaster_id]
        if start is not None:
            where += " AND created_at >= ?"
            args.append(_day_start(start))
        if end is not None:
            where += " AND created_at < ?"
            args.append(_day_start(end + timedelta(days=1)))
        with closing(self._connect()) as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM clips WHERE {where}", args).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM clips WHERE {where} ORDER BY {orders[sort]} LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        clips = [
            Clip(r["id"], r["url"], r["title"], r["thumbnail_url"], r["view_count"],
                 r["duration"], r["creator_name"], r["created_at"])
            for r in rows
        ]
        return clips, total

    def progress(self, broadcaster_id: str, allowed_years: set[int] | None = None) -> Progress:
        expr, extra = _in_scope(allowed_years)
        with closing(self._connect()) as conn:
            w = conn.execute(
                "SELECT COUNT(*) AS total, "
                "COALESCE(SUM(status = 'done'), 0) AS done, "
                "COALESCE(SUM(status = 'done' AND truncated = 1), 0) AS capped "
                "FROM windows WHERE broadcaster_id = ? AND status != 'split'"
                f" AND (status = 'done' OR {expr})",
                [broadcaster_id, *extra],
            ).fetchone()
            clips = conn.execute(
                "SELECT COUNT(*) FROM clips WHERE broadcaster_id = ?", (broadcaster_id,)
            ).fetchone()[0]
        return Progress(w["done"], w["total"], clips, w["capped"])


def _cell_state(leaves: list[sqlite3.Row], span_start: str, span_end: str, count: int) -> str:
    overlapping = [w for w in leaves if w["start"] < span_end and w["end"] > span_start]
    if overlapping and all(w["has_data"] and not w["capped"] for w in overlapping):
        return "exact"
    return "approximate" if count > 0 else "empty"


def _bucket_spans(start: date, end: date, granularity: str) -> list[tuple[str, str, str]]:
    spans = []
    if granularity == "month":
        cur = date(start.year, start.month, 1)
        while cur <= end:
            nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
            spans.append((cur.strftime("%Y-%m"), _day_start(cur), _day_start(nxt)))
            cur = nxt
    else:
        cur = start
        while cur <= end:
            nxt = cur + timedelta(days=1)
            spans.append((cur.isoformat(), _day_start(cur), _day_start(nxt)))
            cur = nxt
    return spans
