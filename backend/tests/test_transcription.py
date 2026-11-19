from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ask import api, answer, transcription
from ask.services import Services
from ask.transcription import ACTIVE, Job, TranscriptionManager
from store import Store
from twitch import User

USAGE = {"prompt_tokens": 1, "output_tokens": 1}


def make(tmp_path, monkeypatch):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(User("1", "jay", "Jay", datetime(2020, 1, 1, tzinfo=timezone.utc)))
    mgr = TranscriptionManager(Services(store, None, None))
    monkeypatch.setattr(transcription, "ensure_range", lambda *a, **k: True)
    return store, mgr, store.get_streamer("jay")


def test_job_reports_progress_in_chunks_and_indexes_after_each_one(tmp_path, monkeypatch):
    store, mgr, streamer = make(tmp_path, monkeypatch)
    monkeypatch.setattr(transcription, "pick_subset", lambda *a, **k: [(f"c{i}", "u") for i in range(120)])
    chunks, indexed = [], []

    def fake_transcribe(conn, chunk, on_clip, should_stop):
        chunks.append(len(chunk))
        for _ in chunk:
            on_clip()
        return len(chunk)

    monkeypatch.setattr(transcription, "transcribe_missing", fake_transcribe)
    monkeypatch.setattr(transcription, "build_vectors", lambda conn: indexed.append("vectors"))
    monkeypatch.setattr(transcription, "add_missing", lambda conn: indexed.append("keywords"))
    job = Job()
    mgr._run(streamer, job)
    assert chunks == [50, 50, 20] and indexed.count("vectors") == 3 and indexed.count("keywords") == 3
    assert (job.state, job.processed, job.total) == ("done", 120, 120)


def test_a_streamer_with_no_clips_ends_in_a_clear_error(tmp_path, monkeypatch):
    store, mgr, streamer = make(tmp_path, monkeypatch)
    monkeypatch.setattr(transcription, "pick_subset", lambda *a, **k: [])
    job = Job()
    mgr._run(streamer, job)
    assert job.state == "error" and "No clips" in job.error


def test_starting_twice_queues_one_job_and_an_error_can_be_retried(tmp_path, monkeypatch):
    store, mgr, streamer = make(tmp_path, monkeypatch)
    monkeypatch.setattr(mgr, "_worker", lambda: None)
    assert mgr.start(streamer)["state"] == "queued"
    mgr.start(streamer)
    assert mgr._queue.qsize() == 1
    mgr._jobs[streamer.broadcaster_id].state = "error"
    mgr.start(streamer)
    assert mgr._queue.qsize() == 2 and mgr.status(streamer)["state"] == "queued"


def test_status_without_a_job_reflects_existing_transcripts(tmp_path, monkeypatch):
    store, mgr, streamer = make(tmp_path, monkeypatch)
    assert mgr.status(streamer)["state"] == "idle"
    import sqlite3
    with sqlite3.connect(store.path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS transcripts (clip_id TEXT PRIMARY KEY, text TEXT, model TEXT, download_s REAL, transcribe_s REAL)")
        conn.execute("INSERT INTO clips VALUES ('c1', '1', 'u', 't', '', 1, 1.0, 'x', '2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO transcripts VALUES ('c1', 'hello', 'm', 1, 1)")
    assert mgr.status(streamer)["state"] == "done" and mgr.status(streamer)["transcribed"] == 1


class FakeTranscriber:
    def __init__(self, state="queued"):
        self.state, self.started = state, []

    def _status(self, streamer):
        return {"login": streamer.login, "display_name": streamer.display_name, "state": self.state,
                "total": 10, "processed": 3, "transcribed": 3, "error": None}

    def start(self, streamer):
        self.started.append(streamer.login)
        return self._status(streamer)

    status = _status


def search_flow(monkeypatch, have, transcriber):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: ("clips", USAGE))
    monkeypatch.setattr(answer, "route", lambda q, d: {"tool": "search_clips", "args": {"streamer": "jay", "query": "chess"}, "usage": USAGE})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: have)
    monkeypatch.setattr(answer, "search_clips", lambda conn, *a, **k: {"results": [{"id": "c", "title": "t", "created_at": "2026-01-01T00:00:00Z", "transcript": "x"}], "confident": True, "unseen_words": []})
    monkeypatch.setattr(answer, "_generate", lambda *a: ("He plays chess [1].", USAGE))


def service(tmp_path, transcriber):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(User("1", "jay", "Jay", datetime(2020, 1, 1, tzinfo=timezone.utc)))
    return Services(store, None, None, transcriber)


def test_topic_search_on_an_untranscribed_streamer_starts_transcribing(tmp_path, monkeypatch):
    t = FakeTranscriber()
    search_flow(monkeypatch, 0, t)
    r = answer.ask(service(tmp_path, t), "clips about chess", None)
    assert t.started == ["jay"] and r["transcription"]["state"] == "queued" and "started now" in r["answer"]
    assert r["confident"] is False


def test_topic_search_while_transcribing_works_on_what_is_done_and_says_so(tmp_path, monkeypatch):
    t = FakeTranscriber("transcribing")
    search_flow(monkeypatch, 3, t)
    r = answer.ask(service(tmp_path, t), "clips about chess", None)
    assert r["transcription"]["state"] == "transcribing" and "Still transcribing" in r["note"] and r["answer"].startswith("He plays chess")


def test_a_finished_streamer_gets_no_progress_block(tmp_path, monkeypatch):
    t = FakeTranscriber("done")
    search_flow(monkeypatch, 50, t)
    assert "transcription" not in answer.ask(service(tmp_path, t), "clips about chess", None)


def test_auto_transcription_can_be_switched_off(tmp_path, monkeypatch):
    t = FakeTranscriber()
    search_flow(monkeypatch, 0, t)
    monkeypatch.setenv("SHIMACLIPS_TRANSCRIBE", "0")
    r = answer.ask(service(tmp_path, t), "clips about chess", None)
    assert t.started == [] and "can't search by topic" in r["answer"] and "transcription" not in r


def test_endpoints_report_and_start_transcription(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "LOG_PATH", tmp_path / "log.jsonl")
    t = FakeTranscriber("transcribing")
    streamers = {"jay": SimpleNamespace(login="jay", display_name="Jay", broadcaster_id="1")}
    store = SimpleNamespace(path=tmp_path / "t.db", get_streamer=lambda login: streamers.get(login))
    app = FastAPI()
    app.include_router(api.make_router(lambda: store, lambda: None, lambda: None, lambda: t))
    c = TestClient(app)
    assert c.get("/api/streamers/jay/transcribe").json()["state"] == "transcribing"
    assert c.post("/api/streamers/jay/transcribe").status_code == 200 and t.started == ["jay"]
    assert c.get("/api/streamers/nobody/transcribe").status_code == 404
    assert c.get("/api/streamers/..%2Fx/transcribe").status_code == 404
    assert set(ACTIVE) == {"queued", "finding", "transcribing", "indexing"}
