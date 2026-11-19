import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

TITLE_MAX = 60
LIST_LIMIT = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS turns_by_conversation ON conversation_turns (conversation_id, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _title(question: str) -> str:
    one_line = " ".join(question.split())
    return one_line if len(one_line) <= TITLE_MAX else one_line[: TITLE_MAX - 3].rstrip() + "..."


class History:
    def __init__(self, path: Path):
        self.path = Path(path)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def exists(self, conversation_id: str) -> bool:
        with closing(self._connect()) as conn:
            return conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone() is not None

    def add_turn(self, conversation_id: str | None, question: str, result: dict) -> str:
        now = _now()
        with closing(self._connect()) as conn, conn:
            if conversation_id is None:
                conversation_id = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (conversation_id, _title(question), now, now),
                )
            else:
                conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
            conn.execute(
                "INSERT INTO conversation_turns (conversation_id, question, result, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, question, json.dumps(result), now),
            )
        return conversation_id

    def list(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?", (LIST_LIMIT,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, conversation_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            head = conn.execute("SELECT id, title FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
            if head is None:
                return None
            turns = conn.execute(
                "SELECT question, result FROM conversation_turns WHERE conversation_id = ? ORDER BY id", (conversation_id,)
            ).fetchall()
        return {"id": head["id"], "title": head["title"],
                "turns": [{"question": t["question"], "result": json.loads(t["result"])} for t in turns]}

    def rename(self, conversation_id: str, title: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?", (_title(title), conversation_id)
            ).rowcount > 0

    def delete(self, conversation_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            return conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,)).rowcount > 0
