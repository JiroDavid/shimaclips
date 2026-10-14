from datetime import datetime, timezone

import httpx
import pytest

import twitch
from twitch import Clip, TwitchClient, TwitchError, top_clips

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 2, 1, tzinfo=timezone.utc)


def raw_clip(i, views=0):
    return {
        "id": f"c{i}", "url": f"https://clips.twitch.tv/c{i}", "title": f"clip {i}",
        "thumbnail_url": "t.jpg", "view_count": views, "duration": 30.0,
        "creator_name": "x", "created_at": "2026-01-02T00:00:00Z",
    }


def make_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TwitchClient("id", "secret", http=http)


def base_handler(on_api):
    def handler(request):
        if request.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return on_api(request)
    return handler


def test_get_user_id_normalizes_login():
    seen = {}

    def on_api(request):
        seen["login"] = request.url.params["login"]
        return httpx.Response(200, json={"data": [{"id": "42"}]})

    client = make_client(base_handler(on_api))
    assert client.get_user_id("  @JasonTheWeen ") == "42"
    assert seen["login"] == "jasontheween"


def test_get_user_id_unknown_returns_none():
    client = make_client(base_handler(lambda r: httpx.Response(200, json={"data": []})))
    assert client.get_user_id("nobody") is None


def test_get_clips_sends_utc_window_and_parses():
    seen = {}

    def on_api(request):
        seen.update(request.url.params)
        return httpx.Response(200, json={"data": [raw_clip(1, 5)], "pagination": {}})

    clips = make_client(base_handler(on_api)).get_clips("42", START, END)
    assert seen["started_at"] == "2026-01-01T00:00:00Z"
    assert seen["ended_at"] == "2026-02-01T00:00:00Z"
    assert seen["first"] == "100"
    assert clips == [Clip("c1", "https://clips.twitch.tv/c1", "clip 1", "t.jpg", 5, 30.0, "x", "2026-01-02T00:00:00Z")]


def test_get_clips_empty_window():
    client = make_client(base_handler(lambda r: httpx.Response(200, json={"data": [], "pagination": {}})))
    assert client.get_clips("42", START, END) == []


def test_get_clips_paginates_until_no_cursor():
    def on_api(request):
        if request.url.params.get("after") == "p2":
            return httpx.Response(200, json={"data": [raw_clip(3)], "pagination": {}})
        return httpx.Response(200, json={"data": [raw_clip(1), raw_clip(2)], "pagination": {"cursor": "p2"}})

    assert len(make_client(base_handler(on_api)).get_clips("42", START, END)) == 3


def test_get_clips_caps_total(monkeypatch):
    monkeypatch.setattr(twitch, "MAX_CLIPS", 250)
    page = {"data": [raw_clip(i) for i in range(100)], "pagination": {"cursor": "more"}}
    client = make_client(base_handler(lambda r: httpx.Response(200, json=page)))
    assert len(client.get_clips("42", START, END)) == 250


def test_401_refreshes_token_once_then_succeeds():
    calls = {"api": 0, "token": 0}

    def handler(request):
        if request.url.host == "id.twitch.tv":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok{calls['token']}", "expires_in": 3600})
        calls["api"] += 1
        if request.headers["Authorization"] == "Bearer tok1":
            return httpx.Response(401)
        return httpx.Response(200, json={"data": [{"id": "42"}]})

    assert make_client(handler).get_user_id("a") == "42"
    assert calls["token"] == 2


def test_persistent_401_raises_readable_error():
    def handler(request):
        if request.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(401)

    with pytest.raises(TwitchError):
        make_client(handler).get_user_id("a")


def test_bad_credentials_raise():
    client = make_client(lambda r: httpx.Response(400, json={"message": "invalid client"}))
    with pytest.raises(TwitchError, match="client ID and secret"):
        client.get_user_id("a")


def test_top_clips_sorts_by_views_and_truncates():
    clips = [Clip(f"c{i}", "u", "t", "", v, 1.0, "x", "d") for i, v in enumerate([5, 90, 20, 90, 1])]
    top = top_clips(clips, 3)
    assert [c.view_count for c in top] == [90, 90, 20]


def test_top_clips_n_larger_than_available():
    clips = [Clip("a", "u", "t", "", 1, 1.0, "x", "d")]
    assert top_clips(clips, 15) == clips
