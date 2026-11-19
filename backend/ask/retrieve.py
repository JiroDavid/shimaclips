import sqlite3
from dataclasses import dataclass

import numpy as np

from ask.embed import EMBED_MODEL, embed_query


@dataclass
class Hit:
    clip_id: str
    score: float


def load_matrix(conn: sqlite3.Connection, kind: str) -> tuple[list[str], np.ndarray]:
    rows = conn.execute(
        "SELECT clip_id, vec FROM clip_vectors WHERE kind = ? AND model = ?", (kind, EMBED_MODEL)
    ).fetchall()
    ids = [r[0] for r in rows]
    mat = np.vstack([np.frombuffer(r[1], dtype=np.float32) for r in rows]) if rows else np.zeros((0, 1), np.float32)
    return ids, mat


def top_k(query_vec: np.ndarray, ids: list[str], mat: np.ndarray, k: int = 5, min_score: float = 0.0) -> list[Hit]:
    if not ids:
        return []
    scores = mat @ query_vec
    order = np.argsort(-scores)[:k]
    return [Hit(ids[i], float(scores[i])) for i in order if scores[i] >= min_score]


def search(conn: sqlite3.Connection, query: str, kind: str = "transcript", k: int = 5, min_score: float = 0.0) -> list[Hit]:
    ids, mat = load_matrix(conn, kind)
    return top_k(embed_query(query), ids, mat, k, min_score)
