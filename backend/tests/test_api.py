import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from loader import LoadManager
from store import Store
from twitch import ChannelHit, Clip, ClipsResult, TwitchError, User


CREATED = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeTwitch:
    def __init__(self, logins=("jason",), error=None, hits=()):
        self.hits = list(hits)
        self.searched = []
        self.users = {l: User(str(i + 1), l, l.title(), CREATED) for i, l in enumerate(logins)}
        self.error = error

    def get_user(self, login):
        if self.error:
            raise self.error
        return self.users.get(login)

    def fetch_window(self, broadcaster_id, start, end):
        return ClipsResult([], False)

    def search_channels(self, query, limit=8):
        if self.error:
            raise self.error
        self.searched.append(query)
        return self.hits[:limit]


def clip(i, views, created="2026-01-02T00:00:00Z"):
    return Clip(f"c{i}", f"https://clips.twitch.tv/c{i}", f"clip {i}", "t.jpg", views, 10.0, "x", created)


@pytest.fixture
def api(tmp_path):
    managers = []

    def make(fake=None):
        store = Store(tmp_path / "api.db")
        mgr = LoadManager(store, lambda: fake or FakeTwitch())
        managers.append(mgr)
        main.app.dependency_overrides[main.get_store] = lambda: store
        main.app.dependency_overrides[main.get_manager] = lambda: mgr
        c = TestClient(main.app)
        c.store, c.mgr = store, mgr
        return c

    yield make
    for m in managers:
        m.shutdown()
    main.app.dependency_overrides.clear()


def wait_done(c, login="jason"):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        st = c.mgr.state(login)
        if st and st.status in ("done", "error"):
            return st
        time.sleep(0.01)
    raise AssertionError("load did not finish")


def test_load_returns_streamer_and_state(api):
    r = api().post("/api/streamers/@Jason/load")
    assert r.status_code == 200
    body = r.json()
    assert body["streamer"] == {"login": "jason", "display_name": "Jason", "account_created": "2020-01-01T00:00:00Z"}
    assert set(body["state"]) == {"status", "error", "windows_done", "windows_total", "clips", "capped", "started_at"}


def test_load_unknown_streamer_404(api):
    r = api().post("/api/streamers/nobody/load")
    assert r.status_code == 404
    assert r.json()["detail"] == "Streamer 'nobody' not found"


@pytest.mark.parametrize("login", ["a-b", "a" * 30])
def test_load_rejects_bad_login_422(api, login):
    assert api().post(f"/api/streamers/{login}/load").status_code == 422


def test_load_rejects_bad_mode_422(api):
    assert api().post("/api/streamers/jason/load?mode=weird").status_code == 422


def test_load_twitch_failure_502(api):
    r = api(FakeTwitch(error=TwitchError("boom"))).post("/api/streamers/jason/load")
    assert r.status_code == 502
    assert r.json()["detail"] == "boom"


def test_calendar_zero_fills_and_flags_ready(api):
    c = api()
    c.post("/api/streamers/jason/load")
    wait_done(c)
    bid = c.store.get_streamer("jason").broadcaster_id
    c.store.upsert_clips(bid, [clip(1, 5, "2026-01-02T00:00:00Z"), clip(2, 6, "2026-01-03T00:00:00Z")])
    r = c.get("/api/streamers/jason/calendar?granularity=month&start=2025-12-01&end=2026-02-28")
    assert r.status_code == 200
    buckets = {b["key"]: b for b in r.json()["buckets"]}
    assert list(buckets) == ["2025-12", "2026-01", "2026-02"]
    assert buckets["2025-12"]["count"] == 0
    assert buckets["2026-01"]["count"] == 2
    assert buckets["2026-01"]["ready"] is True
    assert set(buckets["2026-01"]) == {"key", "count", "ready"}


def test_calendar_unknown_streamer_404(api):
    r = api().get("/api/streamers/jason/calendar?granularity=day&start=2026-01-01&end=2026-01-02")
    assert r.status_code == 404


@pytest.mark.parametrize("query", [
    "granularity=day&start=2026-01-10&end=2026-01-01",
    "granularity=day&start=2025-01-01&end=2026-02-06",
    "granularity=week&start=2026-01-01&end=2026-01-02",
    "granularity=day&start=nope&end=2026-01-02",
])
def test_calendar_rejects_inverted_or_oversized_range(api, query):
    c = api()
    c.post("/api/streamers/jason/load")
    assert c.get(f"/api/streamers/jason/calendar?{query}").status_code == 422


def test_clips_sorted_by_views_with_total_and_offset(api):
    c = api()
    c.post("/api/streamers/jason/load")
    wait_done(c)
    bid = c.store.get_streamer("jason").broadcaster_id
    c.store.upsert_clips(bid, [clip(1, 5), clip(2, 50), clip(3, 20), clip(4, 1, "2026-03-01T00:00:00Z")])
    r = c.get("/api/streamers/jason/clips?start=2026-01-01&end=2026-01-31&limit=2")
    body = r.json()
    assert [x["view_count"] for x in body["clips"]] == [50, 20]
    assert body["total"] == 3
    assert set(body["clips"][0]) == {"id", "url", "title", "thumbnail_url", "view_count", "duration", "creator_name", "created_at"}
    r = c.get("/api/streamers/jason/clips?start=2026-01-01&end=2026-01-31&limit=2&offset=2")
    assert [x["view_count"] for x in r.json()["clips"]] == [5]
    assert len(c.get("/api/streamers/jason/clips").json()["clips"]) == 4


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "start=2026-02-01&end=2026-01-01"])
def test_clips_rejects_bad_params(api, query):
    c = api()
    c.post("/api/streamers/jason/load")
    assert c.get(f"/api/streamers/jason/clips?{query}").status_code == 422


def test_clips_unknown_streamer_404(api):
    assert api().get("/api/streamers/jason/clips").status_code == 404


def test_events_streams_until_done(api):
    c = api()
    c.post("/api/streamers/jason/load")
    text = c.get("/api/streamers/jason/events").text
    assert last_event(text)["status"] == "done"


def test_events_never_loaded_404(api):
    assert api().get("/api/streamers/jason/events").status_code == 404


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
    clips = [{"url": f"https://clips.twitch.tv/u{i}", "title": f"t{i}", "view_count": i} for i in range(2)]
    job_id = c.post("/api/downloads", json={"clips": clips}).json()["job_id"]

    assert last_event(c.get(f"/api/downloads/{job_id}/events").text)["status"] == "done"

    r = c.get(f"/api/downloads/{job_id}/file")
    assert r.status_code == 200
    assert "clips.zip" in r.headers["content-disposition"]
    assert c.get(f"/api/downloads/{job_id}/file").status_code == 404


def test_download_partial_failure_still_delivers(api, monkeypatch):
    monkeypatch.setattr(main, "start_job", fake_start_job(fail_urls={"https://clips.twitch.tv/u1"}))
    c = api(FakeTwitch())
    clips = [{"url": f"https://clips.twitch.tv/u{i}", "title": f"t{i}", "view_count": i} for i in range(3)]
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
    job_id = c.post("/api/downloads", json={"clips": [{"url": "https://clips.twitch.tv/u", "title": "t", "view_count": 1}]}).json()["job_id"]
    assert c.get(f"/api/downloads/{job_id}/file").status_code == 409


@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "https://evil.example/clip",
    "https://clips.twitch.tv.evil.example/x",
    "https://user:pw@clips.twitch.tv/x",
    "http://clips.twitch.tv/x",
])
def test_download_rejects_non_twitch_urls(api, monkeypatch, url):
    monkeypatch.setattr(main, "start_job", lambda job, clips: None)
    r = api(FakeTwitch()).post("/api/downloads", json={"clips": [{"url": url, "title": "t", "view_count": 1}]})
    assert r.status_code == 422


@pytest.mark.parametrize("url", [
    "https://clips.twitch.tv/AbcSlug",
    "https://www.twitch.tv/jasontheween/clip/AbcSlug",
])
def test_download_accepts_twitch_urls(api, monkeypatch, url):
    monkeypatch.setattr(main, "start_job", lambda job, clips: None)
    r = api(FakeTwitch()).post("/api/downloads", json={"clips": [{"url": url, "title": "t", "view_count": 1}]})
    assert r.status_code == 200


def test_app_shutdown_stops_the_load_manager(monkeypatch):
    calls = []

    class Manager:
        def shutdown(self):
            calls.append("shutdown")

    monkeypatch.setattr(main, "_manager", Manager())
    with TestClient(main.app):
        assert calls == []
    assert calls == ["shutdown"]


def test_load_after_shutdown_returns_503(api):
    c = api()
    c.mgr.shutdown()
    r = c.post("/api/streamers/jason/load")
    assert r.status_code == 503


def search_client(api, fake):
    c = api(fake)
    main.app.dependency_overrides[main.get_twitch] = lambda: fake
    return c


def test_search_returns_results_with_avatar_and_live_flag(api):
    fake = FakeTwitch(hits=[ChannelHit("1", "jason", "Jason", "https://x/a.png", True)])
    r = search_client(api, fake).get("/api/streamers/search?q=%20jas%20")
    assert r.status_code == 200
    assert r.json() == {"results": [
        {"login": "jason", "display_name": "Jason", "avatar_url": "https://x/a.png", "is_live": True}
    ]}
    assert fake.searched == ["jas"]


@pytest.mark.parametrize("q", ["", "a", "  a  ", "a" * 41])
def test_search_rejects_short_and_long_queries_422(api, q):
    r = search_client(api, FakeTwitch()).get("/api/streamers/search", params={"q": q})
    assert r.status_code == 422
    assert r.json()["detail"] == "Search must be 2-40 characters"


def test_search_twitch_error_502(api):
    r = search_client(api, FakeTwitch(error=TwitchError("boom"))).get("/api/streamers/search?q=jas")
    assert r.status_code == 502
    assert r.json()["detail"] == "boom"


def test_search_does_not_collide_with_login_routes(api):
    fake = FakeTwitch(hits=[ChannelHit("1", "jason", "Jason", "u", False)])
    c = search_client(api, fake)
    r = c.get("/api/streamers/search?q=jas")
    assert r.status_code == 200 and "results" in r.json()
    assert c.get("/api/streamers/search/clips").status_code == 404


def test_put_year_toggles_and_validates(api):
    c = api()
    c.post("/api/streamers/jason/load")
    wait_done(c)
    now_year = datetime.now(timezone.utc).year
    r = c.put("/api/streamers/Jason/years/2019", json={"enabled": True})
    assert r.status_code == 200 and r.json() == {"year": 2019, "enabled": True}
    assert 2019 in c.store.exact_years("1", now_year)
    r = c.put("/api/streamers/jason/years/2019", json={"enabled": False})
    assert r.json() == {"year": 2019, "enabled": False}
    assert 2019 not in c.store.exact_years("1", now_year)
    assert c.put("/api/streamers/nobody/years/2019", json={"enabled": True}).status_code == 404
    assert c.put("/api/streamers/jason/years/2004", json={"enabled": True}).status_code == 422
    assert c.put(f"/api/streamers/jason/years/{now_year + 2}", json={"enabled": True}).status_code == 422
    assert c.put(f"/api/streamers/jason/years/{now_year + 1}", json={"enabled": True}).status_code == 200
    assert c.put("/api/streamers/jason/years/2019", json={}).status_code == 422
