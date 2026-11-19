import sqlite3

import numpy as np

from ask.embed import embed_query
from ask.keyword import fuse, keyword_search, unseen_words
from ask.retrieve import Hit, load_matrix, top_k
from ask.tools import MAX_LIMIT, ToolError, _broadcaster

STRONG_MATCH = 0.70


def search_clips(conn: sqlite3.Connection, login: str, query: str, limit: int = 5, mode: str = "hybrid") -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ToolError("query must be a non-empty string")
    if mode not in ("hybrid", "embedding", "keyword"):
        raise ToolError("mode must be hybrid, embedding or keyword")
    bid = _broadcaster(conn, login)
    limit = max(1, min(int(limit), MAX_LIMIT))
    query = query.strip()
    ids, mat = load_matrix(conn, "transcript")
    qv = embed_query(query)
    cosine = dict(zip(ids, (mat @ qv).tolist())) if ids else {}
    wide = limit * 5
    emb = top_k(qv, ids, mat, k=wide)
    kw = keyword_search(conn, query, k=wide)
    ranked = {"embedding": emb, "keyword": kw, "hybrid": fuse([emb, kw], k=wide)}[mode]
    results = []
    for h in ranked:
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
        d["score"] = round(cosine.get(h.clip_id, 0.0), 3)
        results.append(d)
        if len(results) == limit:
            break
    best = max((r["score"] for r in results), default=0.0)
    unseen = unseen_words(conn, query)
    confident = bool(results) and not (unseen and best < STRONG_MATCH)
    return {"login": login, "query": query, "results": results, "confident": confident, "unseen_words": unseen}
