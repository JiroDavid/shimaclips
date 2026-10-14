import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from twitch import Clip, TwitchError


class FakeTwitch:
    def __init__(self, user="42", clips=None, error=None):
        self.user, self.clips, self.error = user, clips or [], error
        self.window = None

    def get_user_id(self, login):
        if self.error:
            raise self.error
        return self.user

    def get_clips(self, broadcaster_id, start, end):
        self.window = (start, end)
        return self.clips


def clip(i, views):
    return Clip(f"c{i}", f"https://clips.twitch.tv/c{i}", f"clip {i}", "t.jpg", views, 10.0, "x", "d")


@pytest.fixture
def api():
    def make(fake):
        main.app.dependency_overrides[main.get_twitch] = lambda: fake
        return TestClient(main.app)

    yield make
    main.app.dependency_overrides.clear()


def test_search_returns_top_n_sorted(api):
    fake = FakeTwitch(clips=[clip(1, 5), clip(2, 50), clip(3, 20)])
    r = api(fake).post("/api/clips/search", json={"streamer": "jason", "month": "2026-01", "count": 2})
    assert r.status_code == 200
    body = r.json()
    assert [c["view_count"] for c in body["clips"]] == [50, 20]
    assert body["total_in_window"] == 3
    assert fake.window[0].isoformat() == "2026-01-01T00:00:00+00:00"


def test_search_empty_window_is_ok(api):
    r = api(FakeTwitch(clips=[])).post("/api/clips/search", json={"streamer": "j", "month": "2026-01"})
    assert r.status_code == 200
    assert r.json() == {"clips": [], "total_in_window": 0}


def test_search_custom_range(api):
    fake = FakeTwitch(clips=[clip(1, 1)])
    r = api(fake).post("/api/clips/search", json={"streamer": "j", "start": "2026-01-05", "end": "2026-01-06"})
    assert r.status_code == 200
    assert fake.window[1].isoformat() == "2026-01-07T00:00:00+00:00"


def test_search_unknown_streamer_404(api):
    r = api(FakeTwitch(user=None)).post("/api/clips/search", json={"streamer": "nobody", "month": "2026-01"})
    assert r.status_code == 404
    assert "nobody" in r.json()["detail"]


def test_search_twitch_error_502(api):
    r = api(FakeTwitch(error=TwitchError("boom"))).post("/api/clips/search", json={"streamer": "j", "month": "2026-01"})
    assert r.status_code == 502
    assert r.json()["detail"] == "boom"


@pytest.mark.parametrize("body", [
    {"streamer": "j"},
    {"streamer": "j", "month": "2026-13"},
    {"streamer": "j", "month": "2026-01", "count": 0},
    {"streamer": "j", "start": "2026-01-10", "end": "2026-01-01"},
    {"streamer": "  ", "month": "2026-01"},
])
def test_search_invalid_input_422(api, body):
    assert api(FakeTwitch()).post("/api/clips/search", json=body).status_code == 422


def fake_start_job(fail_urls=()):
    def start(job, clips):
        def fetch(url, dest_dir, basename, on_progress):
            if url in fail_urls:
                raise RuntimeError("gone")
            p = Path(dest_dir) / f"{basename}.mp4"
            p.write_bytes(b"data")
            return p
        main.run_job(job, clips, fetch=fetch)
    return start


def last_event(text):
    return json.loads([l for l in text.splitlines() if l.startswith("data:")][-1][5:])


def test_download_flow_zip(api, monkeypatch):
    monkeypatch.setattr(main, "start_job", fake_start_job())
    c = api(FakeTwitch())
    clips = [{"url": f"u{i}", "title": f"t{i}", "view_count": i} for i in range(2)]
    job_id = c.post("/api/downloads", json={"clips": clips}).json()["job_id"]

    assert last_event(c.get(f"/api/downloads/{job_id}/events").text)["status"] == "done"

    r = c.get(f"/api/downloads/{job_id}/file")
    assert r.status_code == 200
    assert "clips.zip" in r.headers["content-disposition"]
    assert c.get(f"/api/downloads/{job_id}/file").status_code == 404


def test_download_partial_failure_still_delivers(api, monkeypatch):
    monkeypatch.setattr(main, "start_job", fake_start_job(fail_urls={"u1"}))
    c = api(FakeTwitch())
    clips = [{"url": f"u{i}", "title": f"t{i}", "view_count": i} for i in range(3)]
    job_id = c.post("/api/downloads", json={"clips": clips}).json()["job_id"]
    last = last_event(c.get(f"/api/downloads/{job_id}/events").text)
    assert last["status"] == "done"
    assert [i["status"] for i in last["items"]] == ["done", "failed", "done"]


def test_download_empty_list_422(api):
    assert api(FakeTwitch()).post("/api/downloads", json={"clips": []}).status_code == 422


def test_file_unknown_job_404(api):
    assert api(FakeTwitch()).get("/api/downloads/nope/file").status_code == 404
    assert api(FakeTwitch()).get("/api/downloads/nope/events").status_code == 404


def test_file_before_done_409(api, monkeypatch):
    monkeypatch.setattr(main, "start_job", lambda job, clips: None)
    c = api(FakeTwitch())
    job_id = c.post("/api/downloads", json={"clips": [{"url": "u", "title": "t", "view_count": 1}]}).json()["job_id"]
    assert c.get(f"/api/downloads/{job_id}/file").status_code == 409
