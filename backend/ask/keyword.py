import re
import sqlite3

from ask.retrieve import Hit

SCHEMA = "CREATE VIRTUAL TABLE IF NOT EXISTS clip_fts USING fts5(clip_id UNINDEXED, title, text)"
_WORD = re.compile(r"[a-z0-9']+")
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "is", "are", "was", "were", "he",
    "his", "him", "she", "her", "they", "it", "that", "this", "about", "with", "talks", "talk", "talking",
    "clips", "clip", "find", "show", "me", "when", "did", "do", "does", "where", "what", "who", "how",
}


def rebuild(conn: sqlite3.Connection) -> int:
    conn.execute(SCHEMA)
    conn.execute("DELETE FROM clip_fts")
    conn.execute(
        "INSERT INTO clip_fts (clip_id, title, text) "
        "SELECT t.clip_id, k.title, t.text FROM transcripts t JOIN clips k ON k.id = t.clip_id"
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM clip_fts").fetchone()[0]


def match_query(question: str) -> str | None:
    words = [w for w in _WORD.findall(question.lower()) if w not in _STOP and len(w) > 1]
    if not words:
        return None
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words))


def keyword_search(conn: sqlite3.Connection, question: str, k: int = 5, include_title_only: bool = True) -> list[Hit]:
    q = match_query(question)
    if q is None:
        return []
    cols = "title, text" if include_title_only else "text"
    rows = conn.execute(
        f"SELECT clip_id, bm25(clip_fts) FROM clip_fts WHERE clip_fts MATCH ? ORDER BY bm25(clip_fts) LIMIT ?",
        (f"{{{cols.replace(', ', ' ')}}} : ({q})", k),
    ).fetchall()
    return [Hit(r[0], -float(r[1])) for r in rows]


def fuse(rankings: list[list[Hit]], k: int = 5, c: int = 60) -> list[Hit]:
    scores: dict[str, float] = {}
    for hits in rankings:
        for rank, h in enumerate(hits):
            scores[h.clip_id] = scores.get(h.clip_id, 0.0) + 1.0 / (c + rank + 1)
    top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
    return [Hit(cid, s) for cid, s in top]
