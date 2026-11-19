from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ask import api
from ask.history import History

RESULT = {"question": "q", "kind": "answer", "tool": "count_clips", "args": {}, "confident": True,
          "usage": {"prompt_tokens": 1, "output_tokens": 1}, "seconds": 0.1, "answer": "x", "sources": []}


def client(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(api, "ask", lambda svc, q, login: dict(RESULT, question=q))
    store = SimpleNamespace(path=tmp_path / "t.db")
    app = FastAPI()
    app.include_router(api.make_router(lambda: store, lambda: None, lambda: None))
    return TestClient(app)


def test_first_question_creates_a_conversation_titled_from_it(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    r = c.post("/api/ask", json={"question": "how many clips this month"}).json()
    listed = c.get("/api/conversations").json()["conversations"]
    assert [x["id"] for x in listed] == [r["conversation_id"]] and listed[0]["title"] == "how many clips this month"


def test_follow_up_joins_the_same_conversation_in_order(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    cid = c.post("/api/ask", json={"question": "first question"}).json()["conversation_id"]
    again = c.post("/api/ask", json={"question": "second question", "conversation_id": cid}).json()
    assert again["conversation_id"] == cid
    turns = c.get(f"/api/conversations/{cid}").json()["turns"]
    assert [t["question"] for t in turns] == ["first question", "second question"]
    assert turns[0]["result"]["answer"] == "x"


def test_most_recently_used_conversation_is_listed_first(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    a = c.post("/api/ask", json={"question": "conversation a"}).json()["conversation_id"]
    b = c.post("/api/ask", json={"question": "conversation b"}).json()["conversation_id"]
    c.post("/api/ask", json={"question": "more on a", "conversation_id": a})
    assert [x["id"] for x in c.get("/api/conversations").json()["conversations"]] == [a, b]


def test_unknown_or_malformed_ids_are_rejected(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    assert c.post("/api/ask", json={"question": "hello there", "conversation_id": "0" * 32}).status_code == 404
    assert c.post("/api/ask", json={"question": "hello there", "conversation_id": "../etc"}).status_code == 404
    assert c.get("/api/conversations/nope").status_code == 404
    assert c.delete("/api/conversations/" + "0" * 32).status_code == 404


def test_delete_removes_the_conversation_and_its_turns(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    cid = c.post("/api/ask", json={"question": "to be deleted"}).json()["conversation_id"]
    assert c.delete(f"/api/conversations/{cid}").status_code == 200
    assert c.get(f"/api/conversations/{cid}").status_code == 404
    assert c.get("/api/conversations").json()["conversations"] == []


def test_rename_and_long_titles(monkeypatch, tmp_path):
    c = client(monkeypatch, tmp_path)
    cid = c.post("/api/ask", json={"question": "x" * 200}).json()["conversation_id"]
    assert len(c.get("/api/conversations").json()["conversations"][0]["title"]) <= 60
    assert c.put(f"/api/conversations/{cid}", json={"title": "My rewind"}).status_code == 200
    assert c.get(f"/api/conversations/{cid}").json()["title"] == "My rewind"


def test_history_survives_reopening_the_database(tmp_path):
    h = History(tmp_path / "t.db")
    cid = h.add_turn(None, "hello", RESULT)
    assert History(tmp_path / "t.db").get(cid)["turns"][0]["question"] == "hello"
