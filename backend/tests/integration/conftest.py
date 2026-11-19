import hashlib
import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from fastapi.testclient import TestClient

from jobs import JobStore
from twitch import ChannelHit, Clip, User

CREATED = datetime(2020, 1, 1, tzinfo=timezone.utc)


def recent(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class TwitchWorld:
    def __init__(self):
        self.users: dict[str, User] = {}
        self.clips: dict[str, list[Clip]] = {}
        self.profiles: dict[str, dict] = {}
        self.calls: list[str] = []

    def add_streamer(self, login, uid, bio="", kind="partner", live=False, clips=()):
        self.users[login] = User(uid, login, login.title(), CREATED)
        self.profiles[uid] = {"description": bio, "broadcaster_type": kind, "profile_image_url": "", "is_live": live,
                              "stream_title": "late stream" if live else "", "game_name": "Chess" if live else "", "viewer_count": 3 if live else 0}
        self.clips[uid] = list(clips)
        return self.users[login]

    def rename(self, uid, new_login):
        old = next(u for u in self.users.values() if u.id == uid)
        del self.users[old.login]
        self.users[new_login] = User(uid, new_login, new_login.title(), old.created_at)

    def make_clip(self, uid, clip_id, title, views, days_ago):
        clip = Clip(clip_id, f"https://www.twitch.tv/old/clip/{clip_id}", title, f"https://t/{clip_id}.jpg", views, 30.0, "fan", recent(days_ago))
        self.clips.setdefault(uid, []).append(clip)
        return clip

    def get_user(self, login):
        self.calls.append(f"get_user:{login}")
        return self.users.get(login)

    def get_user_by_id(self, uid):
        return next((u for u in self.users.values() if u.id == uid), None)

    def get_profile(self, uid):
        return self.profiles[uid]

    def search_channels(self, query, limit=8):
        self.calls.append(f"search:{query}")
        hits = [ChannelHit(u.id, u.login, u.display_name, "", False) for u in self.users.values() if query[:3] in u.login]
        return hits[:limit]

    def fetch_top(self, broadcaster_id, start, end, limit):
        self.calls.append(f"fetch_top:{broadcaster_id}")
        def when(c):
            return datetime.fromisoformat(c.created_at.replace("Z", "+00:00"))
        pool = [c for c in self.clips.get(broadcaster_id, []) if (start is None or when(c) >= start) and (end is None or when(c) < end)]
        return sorted(pool, key=lambda c: -c.view_count)[:limit]

    def fetch_window(self, broadcaster_id, start, end):
        from twitch import ClipsResult
        return ClipsResult(self.fetch_top(broadcaster_id, start, end, 1000), False)


class Models:
    """Stands in for the local LLM. Tests script what the guard and router decide."""

    def __init__(self):
        self.label = "clips"
        self.tool = None
        self.args = {}
        self.generated = "It is about that [1]."
        self.router_calls = 0

    def route(self, tool, **args):
        self.tool, self.args = tool, args


def hash_embed(texts, prefix=""):
    out = np.zeros((len(texts), 64), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True).clip(min=1e-9)
    return out / norms


@pytest.fixture
def world():
    return TwitchWorld()


@pytest.fixture
def models(monkeypatch):
    m = Models()
    usage = {"prompt_tokens": 5, "output_tokens": 5}
    monkeypatch.setattr("ask.answer.classify", lambda q, d=None: (m.label, usage))

    def route(q, login):
        m.router_calls += 1
        return {"tool": m.tool, "args": dict(m.args), "usage": usage}

    monkeypatch.setattr("ask.answer.route", route)
    monkeypatch.setattr("ask.answer._generate", lambda q, results: (m.generated, usage))
    monkeypatch.setattr("ask.embed.embed_texts", hash_embed)
    return m


@pytest.fixture
def env(tmp_path, monkeypatch, world, models):
    import main

    monkeypatch.setenv("SHIMACLIPS_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("SHIMACLIPS_CRAWLER", "0")
    monkeypatch.setenv("SHIMACLIPS_WORKDIR", str(tmp_path / "work"))
    for name in ("_store", "_manager", "_live", "_crawler", "_transcriber"):
        monkeypatch.setattr(main, name, None)
    monkeypatch.setattr(main, "_twitch", world)
    monkeypatch.setattr(main, "job_store", JobStore(tmp_path / "jobs"))
    from ask import streamers
    streamers._checked.clear()
    client = TestClient(main.app)
    client.world, client.models, client.tmp = world, models, tmp_path
    client.main = main
    yield client
    if main._transcriber is not None:
        main._transcriber.stop()


def ask(client, question, login=None, conversation_id=None):
    r = client.post("/api/ask", json={"question": question, "login": login, "conversation_id": conversation_id})
    assert r.status_code == 200, r.text
    return r.json()


def load_streamer(env, login, uid, rows=()):
    store = env.main.get_store()
    store.upsert_streamer(User(uid, login, login.title(), CREATED))
    store.upsert_clips(uid, [
        Clip(cid, f"https://www.twitch.tv/{login}/clip/{cid}", title, f"https://t/{cid}.jpg", views, 30.0, "fan", created)
        for cid, title, views, created in rows
    ])
    return store


def index_transcripts(env, items):
    """items: (broadcaster_id, clip_id, text). Builds the real embedding and keyword indexes."""
    import sqlite3
    from ask.embed import build_vectors
    from ask.keyword import rebuild
    from ask.transcribe import ensure_schema

    conn = sqlite3.connect(env.main.get_store().path, timeout=30)
    ensure_schema(conn)
    conn.executemany("INSERT OR REPLACE INTO transcripts VALUES (?, ?, 'test', 0, 0)", [(cid, text) for _b, cid, text in items])
    conn.commit()
    build_vectors(conn)
    rebuild(conn)
    conn.close()
