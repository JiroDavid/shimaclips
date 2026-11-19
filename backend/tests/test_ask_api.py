from fastapi.testclient import TestClient

import main
from ask import api


def test_ask_rejects_bad_login():
    r = TestClient(main.app).post("/api/ask", json={"question": "how many clips", "login": "../etc"})
    assert r.status_code == 422


def test_ask_rejects_short_question():
    r = TestClient(main.app).post("/api/ask", json={"question": "hi", "login": "jay"})
    assert r.status_code == 422


def test_ask_returns_result_and_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(api, "open_readonly", lambda _p: type("C", (), {"close": lambda self: None})())
    fake = {"question": "q", "tool": "count_clips", "args": {}, "confident": True,
            "usage": {"prompt_tokens": 1, "output_tokens": 1}, "seconds": 0.1, "answer": "x", "sources": []}
    monkeypatch.setattr(api, "ask", lambda *_a, **_k: fake)
    r = TestClient(main.app).post("/api/ask", json={"question": "how many clips", "login": "Jay"})
    assert r.status_code == 200 and r.json()["answer"] == "x"
    assert (tmp_path / "log.jsonl").read_text().count("\n") == 1
