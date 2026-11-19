import sqlite3

from ask.keyword import unseen_words
from ask.retrieve import search
from ask.tools import MAX_LIMIT, ToolError, _broadcaster

STRONG_MATCH = 0.70


def search_clips(conn: sqlite3.Connection, login: str, query: str, limit: int = 5, kind: str = "transcript") -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query must be a non-empty string")
    bid = _broadcaster(conn, login)
    limit = max(1, min(int(limit), MAX_LIMIT))
    hits = search(conn, query.strip(), kind=kind, k=limit * 4)
    results = []
    for h in hits:
        row = conn.execute(
            "SELECT k.id, k.title, k.url, k.view_count, k.created_at, t.text "
            "FROM clips k LEFT JOIN transcripts t ON t.clip_id = k.id "
            "WHERE k.id = ? AND k.broadcaster_id = ?",
            (h.clip_id, bid),
        ).fetchone()
        if row is None:
            continue
        d = dict(row)
        d["transcript"] = (d.pop("text") or "")[:300]
        d["score"] = round(h.score, 3)
        results.append(d)
        if len(results) == limit:
            break
    best = results[0]["score"] if results else 0.0
    unseen = unseen_words(conn, query)
    confident = bool(results) and not (unseen and best < STRONG_MATCH)
    return {
        "login": login, "query": query, "results": results, "confident": confident,
        "unseen_words": unseen,
    }
