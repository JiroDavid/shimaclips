import re
import sqlite3

from ask.retrieve import Hit

SCHEMA = "CREATE VIRTUAL TABLE IF NOT EXISTS clip_fts USING fts5(clip_id UNINDEXED, title, text)"
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "at", "for", "and", "or", "is", "are", "was", "were", "he",
    "his", "him", "she", "her", "they", "it", "that", "this", "about", "with", "talks", "talk", "talking",
    "clips", "clip", "mentioned", "mention", "happened", "said", "say", "find", "show", "me", "when", "did", "do", "does", "where", "what", "who", "how",
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


def content_words(question: str) -> list[str]:
    words = [w for w in _WORD.findall(question.lower()) if w not in _STOP and len(w) > 1]
    return list(dict.fromkeys(words))


def add_missing(conn: sqlite3.Connection) -> int:
    conn.execute(SCHEMA)
    conn.execute(
        "INSERT INTO clip_fts (clip_id, title, text) "
        "SELECT t.clip_id, k.title, t.text FROM transcripts t JOIN clips k ON k.id = t.clip_id "
        "WHERE t.clip_id NOT IN (SELECT clip_id FROM clip_fts)"
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM clip_fts").fetchone()[0]


def match_query(question: str) -> str | None:
    words = content_words(question)
    if not words:
        return None
    return " OR ".join(f'"{w}"' for w in words)


def unseen_words(conn: sqlite3.Connection, question: str, broadcaster_id: str | None = None) -> list[str]:
    missing = []
    for w in content_words(question):
        if broadcaster_id is None:
            n = conn.execute("SELECT COUNT(*) FROM clip_fts WHERE clip_fts MATCH ?", (f'"{w}"',)).fetchone()[0]
        else:
            n = conn.execute(
                "SELECT COUNT(*) FROM clip_fts JOIN clips k ON k.id = clip_fts.clip_id "
                "WHERE clip_fts MATCH ? AND k.broadcaster_id = ?",
                (f'"{w}"', broadcaster_id),
            ).fetchone()[0]
        if n == 0:
            missing.append(w)
    return missing


def keyword_search(
    conn: sqlite3.Connection, question: str, k: int = 5, include_title_only: bool = True, broadcaster_id: str | None = None
) -> list[Hit]:
    q = match_query(question)
    if q is None:
        return []
    cols = "title, text" if include_title_only else "text"
    scope = "JOIN clips k ON k.id = clip_fts.clip_id" if broadcaster_id is not None else ""
    where = "AND k.broadcaster_id = ?" if broadcaster_id is not None else ""
    args = [f"{{{cols.replace(', ', ' ')}}} : ({q})"] + ([broadcaster_id] if broadcaster_id is not None else []) + [k]
    rows = conn.execute(
        f"SELECT clip_fts.clip_id, bm25(clip_fts) FROM clip_fts {scope} WHERE clip_fts MATCH ? {where} "
        "ORDER BY bm25(clip_fts) LIMIT ?",
        args,
    ).fetchall()
    return [Hit(r[0], -float(r[1])) for r in rows]


def fuse(rankings: list[list[Hit]], k: int = 5, c: int = 60) -> list[Hit]:
    scores: dict[str, float] = {}
    for hits in rankings:
        for rank, h in enumerate(hits):
            scores[h.clip_id] = scores.get(h.clip_id, 0.0) + 1.0 / (c + rank + 1)
    top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
    return [Hit(cid, s) for cid, s in top]
