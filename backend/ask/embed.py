import sqlite3

import httpx
import numpy as np

OLLAMA = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

SCHEMA = """
CREATE TABLE IF NOT EXISTS clip_vectors (
    clip_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    model TEXT NOT NULL,
    vec BLOB NOT NULL,
    PRIMARY KEY (clip_id, kind, model)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def embed_texts(texts: list[str], prefix: str = "search_document: ") -> np.ndarray:
    resp = httpx.post(
        f"{OLLAMA}/api/embed",
        json={"model": EMBED_MODEL, "input": [prefix + t for t in texts]},
        timeout=120,
    )
    resp.raise_for_status()
    vecs = np.array(resp.json()["embeddings"], dtype=np.float32)
    return vecs / np.linalg.norm(vecs, axis=1, keepdims=True).clip(min=1e-9)


def embed_query(text: str) -> np.ndarray:
    return embed_texts([text], prefix="search_query: ")[0]


def build_vectors(conn: sqlite3.Connection, batch: int = 32) -> int:
    ensure_schema(conn)
    pending = conn.execute(
        "SELECT t.clip_id, k.title, t.text FROM transcripts t JOIN clips k ON k.id = t.clip_id "
        "WHERE NOT EXISTS (SELECT 1 FROM clip_vectors v WHERE v.clip_id = t.clip_id "
        "AND v.kind = 'transcript' AND v.model = ?)",
        (EMBED_MODEL,),
    ).fetchall()
    n = 0
    for i in range(0, len(pending), batch):
        chunk = pending[i:i + batch]
        docs = [f"{title}. {text}" if text else title for _, title, text in chunk]
        titles = [title for _, title, _ in chunk]
        for kind, texts in (("transcript", docs), ("title", titles)):
            vecs = embed_texts(texts)
            conn.executemany(
                "INSERT OR REPLACE INTO clip_vectors VALUES (?, ?, ?, ?)",
                [(cid, kind, EMBED_MODEL, v.tobytes()) for (cid, _, _), v in zip(chunk, vecs)],
            )
        conn.commit()
        n += len(chunk)
    return n
