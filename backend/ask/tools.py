import sqlite3
from datetime import date
from pathlib import Path

MAX_LIMIT = 50


class ToolError(ValueError):
    pass


def open_readonly(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _broadcaster(conn: sqlite3.Connection, login: str) -> str:
    row = conn.execute("SELECT broadcaster_id FROM streamers WHERE login = ?", (login.strip().lower(),)).fetchone()
    if row is None:
        raise ToolError(f"unknown streamer: {login}")
    return row["broadcaster_id"]


def _iso(value: str, name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ToolError(f"{name} must be an ISO date like 2026-11-01") from None


def _range(start: str, end: str) -> tuple[str, str]:
    s, e = _iso(start, "start"), _iso(end, "end")
    if s >= e:
        raise ToolError("start must be before end")
    return s, e


def count_clips(conn: sqlite3.Connection, login: str, start: str, end: str) -> dict:
    s, e = _range(start, end)
    bid = _broadcaster(conn, login)
    n = conn.execute(
        "SELECT COUNT(*) FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ?",
        (bid, s, e),
    ).fetchone()[0]
    return {"login": login, "start": s, "end": e, "count": n}


def top_clips(
    conn: sqlite3.Connection, login: str, start: str, end: str, limit: int = 10, sort: str = "views"
) -> dict:
    s, e = _range(start, end)
    bid = _broadcaster(conn, login)
    if sort not in ("views", "newest"):
        raise ToolError("sort must be views or newest")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        raise ToolError("limit must be an integer") from None
    limit = max(1, min(limit, MAX_LIMIT))
    order = "view_count DESC" if sort == "views" else "created_at DESC"
    rows = conn.execute(
        f"SELECT id, title, url, view_count, created_at FROM clips "
        f"WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ? ORDER BY {order} LIMIT ?",
        (bid, s, e, limit),
    ).fetchall()
    return {"login": login, "start": s, "end": e, "clips": [dict(r) for r in rows]}
