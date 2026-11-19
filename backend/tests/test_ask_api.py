from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ask import api


def client(monkeypatch, tmp_path, result=None):
    monkeypatch.setattr(api, "LOG_PATH", tmp_path / "log.jsonl")
    fake = result or {"question": "q", "kind": "answer", "tool": "count_clips", "args": {}, "confident": True,
                      "usage": {"prompt_tokens": 1, "output_tokens": 1}, "seconds": 0.1, "answer": "x"}
    seen = {}

    def fake_ask(svc, question, login):
        seen["login"] = login
        return fake

    monkeypatch.setattr(api, "ask", fake_ask)
    app = FastAPI()
    store = SimpleNamespace(path=tmp_path / "t.db")
    app.include_router(api.make_router(lambda: store, lambda: object(), lambda: None))
    return TestClient(app), seen


def test_rejects_bad_login(monkeypatch, tmp_path):
    c, _ = client(monkeypatch, tmp_path)
    assert c.post("/api/ask", json={"question": "how many clips", "login": "../etc"}).status_code == 422


def test_rejects_short_question(monkeypatch, tmp_path):
    c, _ = client(monkeypatch, tmp_path)
    assert c.post("/api/ask", json={"question": "hi"}).status_code == 422


def test_login_is_optional_and_normalised(monkeypatch, tmp_path):
    c, seen = client(monkeypatch, tmp_path)
    assert c.post("/api/ask", json={"question": "how many clips"}).status_code == 200 and seen["login"] is None
    c.post("/api/ask", json={"question": "how many clips", "login": " Jay "})
    assert seen["login"] == "jay"


def test_result_is_returned_and_logged(monkeypatch, tmp_path):
    c, _ = client(monkeypatch, tmp_path)
    r = c.post("/api/ask", json={"question": "how many clips"})
    assert r.json()["answer"] == "x" and (tmp_path / "log.jsonl").read_text().count("\n") == 1
