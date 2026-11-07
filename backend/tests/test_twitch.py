from datetime import datetime, timezone

import httpx
import pytest

import twitch
from twitch import TwitchClient, TwitchError

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 2, 1, tzinfo=timezone.utc)


def raw_clip(i, views=0):
    return {
        "id": f"c{i}", "url": f"https://clips.twitch.tv/c{i}", "title": f"clip {i}",
        "thumbnail_url": "t.jpg", "view_count": views, "duration": 30.0,
        "creator_name": "x", "created_at": "2026-01-02T00:00:00Z",
    }


USER_JSON = {"id": "42", "login": "a", "display_name": "A", "created_at": "2020-05-06T07:08:09Z"}


def make_client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return TwitchClient("id", "secret", http=http)


def base_handler(on_api):
    def handler(request):
        if request.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return on_api(request)
    return handler


def test_401_refreshes_token_once_then_succeeds():
    calls = {"api": 0, "token": 0}

    def handler(request):
        if request.url.host == "id.twitch.tv":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok{calls['token']}", "expires_in": 3600})
        calls["api"] += 1
        if request.headers["Authorization"] == "Bearer tok1":
            return httpx.Response(401)
        return httpx.Response(200, json={"data": [USER_JSON]})

    assert make_client(handler).get_user("a").id == "42"
    assert calls["token"] == 2


def test_persistent_401_raises_readable_error():
    def handler(request):
        if request.url.host == "id.twitch.tv":
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(401)

    with pytest.raises(TwitchError):
        make_client(handler).get_user("a")


def test_bad_credentials_raise():
    client = make_client(lambda r: httpx.Response(400, json={"message": "invalid client"}))
    with pytest.raises(TwitchError, match="client ID and secret"):
        client.get_user("a")


def test_fetch_window_flags_truncation_at_cap():
    def on_api(request):
        return httpx.Response(200, json={"data": [raw_clip(i) for i in range(100)], "pagination": {"cursor": "more"}})

    result = make_client(base_handler(on_api)).fetch_window("42", START, END)
    assert result.truncated is True
    assert len(result.clips) == 3000


def test_fetch_window_not_truncated_below_cap():
    client = make_client(base_handler(lambda r: httpx.Response(200, json={"data": [raw_clip(1)], "pagination": {}})))
    result = client.fetch_window("42", START, END)
    assert result.truncated is False
    assert len(result.clips) == 1


def test_get_user_returns_created_at_as_utc():
    user_json = {"id": "42", "login": "jason", "display_name": "Jason", "created_at": "2020-05-06T07:08:09Z"}
    client = make_client(base_handler(lambda r: httpx.Response(200, json={"data": [user_json]})))
    user = client.get_user(" @Jason ")
    assert user == twitch.User("42", "jason", "Jason", datetime(2020, 5, 6, 7, 8, 9, tzinfo=timezone.utc))
    assert user.created_at.utcoffset().total_seconds() == 0


def test_get_user_unknown_returns_none():
    client = make_client(base_handler(lambda r: httpx.Response(200, json={"data": []})))
    assert client.get_user("nobody") is None


def test_get_retries_once_after_429_using_retry_after(monkeypatch):
    sleeps = []
    monkeypatch.setattr(twitch.time, "sleep", sleeps.append)
    calls = {"api": 0}

    def on_api(request):
        calls["api"] += 1
        if calls["api"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"data": [USER_JSON]})

    assert make_client(base_handler(on_api)).get_user("a").id == "42"
    assert sleeps == [7]
    assert calls["api"] == 2


def rate_limited_client(responses, monkeypatch, now=1000.0):
    sleeps = []
    monkeypatch.setattr(twitch.time, "sleep", sleeps.append)
    monkeypatch.setattr(twitch, "_now", lambda: now)
    calls = {"api": 0}

    def on_api(request):
        calls["api"] += 1
        i = calls["api"] - 1
        return responses[i] if i < len(responses) else httpx.Response(200, json={"data": [USER_JSON]})

    return make_client(base_handler(on_api)), sleeps, calls


def test_429_waits_until_ratelimit_reset(monkeypatch):
    client, sleeps, calls = rate_limited_client(
        [httpx.Response(429, headers={"Ratelimit-Reset": "1012", "Ratelimit-Remaining": "0"})], monkeypatch
    )
    assert client.get_user("a").id == "42"
    assert sleeps == [12]
    assert calls["api"] == 2


def test_429_prefers_retry_after_and_caps_it(monkeypatch):
    client, sleeps, _ = rate_limited_client(
        [
            httpx.Response(429, headers={"Retry-After": "3", "Ratelimit-Reset": "1050"}),
            httpx.Response(429, headers={"Retry-After": "600"}),
            httpx.Response(429, headers={"Ratelimit-Reset": "5000"}),
        ],
        monkeypatch,
    )
    assert client.get_user("a").id == "42"
    assert sleeps == [3, 60, 60]


def test_429_without_headers_uses_short_default(monkeypatch):
    client, sleeps, _ = rate_limited_client([httpx.Response(429)], monkeypatch)
    client.get_user("a")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 5


def test_429_gives_up_after_six_attempts(monkeypatch):
    client, sleeps, calls = rate_limited_client([httpx.Response(429)] * 10, monkeypatch)
    with pytest.raises(TwitchError, match="429"):
        client.get_user("a")
    assert calls["api"] == 6
    assert len(sleeps) == 5


def test_401_refresh_does_not_use_a_rate_limit_attempt(monkeypatch):
    monkeypatch.setattr(twitch.time, "sleep", lambda s: None)
    monkeypatch.setattr(twitch, "_now", lambda: 1000.0)
    calls = {"api": 0, "token": 0}

    def handler(request):
        if request.url.host == "id.twitch.tv":
            calls["token"] += 1
            return httpx.Response(200, json={"access_token": f"tok{calls['token']}", "expires_in": 3600})
        calls["api"] += 1
        if calls["api"] == 1:
            return httpx.Response(401)
        if calls["api"] <= 6:
            return httpx.Response(429)
        return httpx.Response(200, json={"data": [USER_JSON]})

    assert make_client(handler).get_user("a").id == "42"
    assert calls["api"] == 7 and calls["token"] == 2


def test_low_remaining_paces_next_request_until_reset(monkeypatch):
    ok = lambda remaining, reset: httpx.Response(
        200, json={"data": [USER_JSON]}, headers={"Ratelimit-Remaining": str(remaining), "Ratelimit-Reset": str(reset)}
    )
    client, sleeps, _ = rate_limited_client([ok(50, 1030), ok(2, 1020), ok(2, 9999)], monkeypatch)
    client.get_user("a")
    assert sleeps == []
    client.get_user("a")
    assert sleeps == []
    client.get_user("a")
    assert sleeps == [20]
    client.get_user("a")
    assert sleeps == [20, 60]


def paged_handler(n_pages, per_page):
    def on_api(request):
        page = int(request.url.params.get("after", "0"))
        data = [raw_clip(page * 100 + i) for i in range(per_page)]
        more = {"cursor": str(page + 1)} if page + 1 < n_pages else {}
        return httpx.Response(200, json={"data": data, "pagination": more})
    return base_handler(on_api)


def test_fetch_window_flags_truncation_when_helix_page_limit_is_reached():
    result = make_client(paged_handler(11, 40)).fetch_window("42", START, END)
    assert len(result.clips) == 440
    assert result.truncated is True


def test_fetch_window_with_few_short_pages_is_complete():
    result = make_client(paged_handler(4, 60)).fetch_window("42", START, END)
    assert len(result.clips) == 240
    assert result.truncated is False
