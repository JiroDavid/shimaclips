import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.twitch.tv/helix"
MAX_CLIPS = 3000
# Helix ends pagination after about 11 pages per query even when more clips exist, and its
# pages are often short, so reaching this many pages is the reliable sign of a cut-off result.
HELIX_PAGE_LIMIT = 10
MAX_ATTEMPTS = 6
MAX_SLEEP = 60.0
DEFAULT_BACKOFF = 1.0
PACE_FLOOR = 5


class TwitchError(Exception):
    pass


@dataclass
class Clip:
    id: str
    url: str
    title: str
    thumbnail_url: str
    view_count: int
    duration: float
    creator_name: str
    created_at: str


@dataclass
class User:
    id: str
    login: str
    display_name: str
    created_at: datetime


@dataclass
class ChannelHit:
    id: str
    login: str
    display_name: str
    thumbnail_url: str
    is_live: bool


@dataclass
class ClipsResult:
    clips: list[Clip]
    truncated: bool


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_clip(c: dict) -> Clip:
    return Clip(
        id=c["id"], url=c["url"], title=c["title"], thumbnail_url=c["thumbnail_url"],
        view_count=c["view_count"], duration=c["duration"],
        creator_name=c["creator_name"], created_at=c["created_at"],
    )


def _now() -> float:
    return time.time()


def _header(r: httpx.Response, name: str) -> float | None:
    try:
        return float(r.headers[name])
    except (KeyError, ValueError):
        return None


def _capped(seconds: float) -> float:
    return min(max(seconds, 0.0), MAX_SLEEP)


def _rate_limit_wait(r: httpx.Response) -> float:
    retry_after = _header(r, "Retry-After")
    if retry_after is not None:
        return _capped(retry_after)
    reset = _header(r, "Ratelimit-Reset")
    if reset is not None:
        return _capped(reset - _now())
    return DEFAULT_BACKOFF


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15)
        self._token: str | None = None
        self._expires = 0.0
        self._token_lock = threading.Lock()
        self._limit_lock = threading.Lock()
        self._remaining: float | None = None
        self._reset: float | None = None

    def _fetch_token(self, stale: str | None = None) -> None:
        with self._token_lock:
            if stale is not None and self._token != stale:
                return
            self._fetch_token_locked()

    def _fetch_token_locked(self) -> None:
        r = self._http.post(TOKEN_URL, params={
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        })
        if r.status_code != 200:
            raise TwitchError(f"Twitch auth failed ({r.status_code}). Check your client ID and secret in backend/.env")
        data = r.json()
        self._token = data["access_token"]
        self._expires = time.time() + data["expires_in"] - 60

    def _pace(self) -> None:
        with self._limit_lock:
            if self._remaining is not None and self._remaining < PACE_FLOOR and self._reset is not None:
                time.sleep(_capped(self._reset - _now()))
            self._remaining = None

    def _note_limits(self, r: httpx.Response) -> None:
        remaining = _header(r, "Ratelimit-Remaining")
        reset = _header(r, "Ratelimit-Reset")
        with self._limit_lock:
            self._remaining = remaining
            self._reset = reset

    def _get(self, path: str, params: dict) -> dict:
        if not self._token or time.time() >= self._expires:
            self._fetch_token()
        refreshed = False
        attempts = 0
        while True:
            self._pace()
            token = self._token
            r = self._http.get(f"{API_URL}{path}", params=params, headers={
                "Client-Id": self._client_id,
                "Authorization": f"Bearer {token}",
            })
            if r.status_code == 401 and not refreshed:
                refreshed = True
                self._fetch_token(stale=token)
                continue
            if r.status_code == 429:
                attempts += 1
                if attempts < MAX_ATTEMPTS:
                    time.sleep(_rate_limit_wait(r))
                    continue
            else:
                self._note_limits(r)
            break
        if r.status_code != 200:
            raise TwitchError(f"Twitch API error ({r.status_code})")
        return r.json()

    def get_user(self, login: str) -> User | None:
        login = login.strip().lstrip("@").lower()
        data = self._get("/users", {"login": login})["data"]
        if not data:
            return None
        u = data[0]
        created = datetime.fromisoformat(u["created_at"].replace("Z", "+00:00")).astimezone(timezone.utc)
        return User(id=u["id"], login=u["login"], display_name=u["display_name"], created_at=created)

    def search_channels(self, query: str, limit: int = 8) -> list[ChannelHit]:
        body = self._get("/search/channels", {"query": query, "first": max(limit, 20)})
        hits = [
            ChannelHit(
                id=c["id"], login=c["broadcaster_login"], display_name=c["display_name"],
                thumbnail_url=c["thumbnail_url"], is_live=c["is_live"],
            )
            for c in body["data"]
        ]
        wanted = query.strip().lstrip("@").lower()
        hits.sort(key=lambda h: h.login.lower() != wanted)
        return hits[:limit]

    def fetch_top(self, broadcaster_id: str, start: datetime | None, end: datetime | None, limit: int) -> list[Clip]:
        clips: list[Clip] = []
        cursor = None
        pages = 0
        while len(clips) < limit and pages < HELIX_PAGE_LIMIT:
            params = {"broadcaster_id": broadcaster_id, "first": min(100, limit - len(clips))}
            if start is not None:
                params["started_at"] = _rfc3339(start)
            if end is not None:
                params["ended_at"] = _rfc3339(end)
            if cursor:
                params["after"] = cursor
            body = self._get("/clips", params)
            pages += 1
            clips += [_to_clip(c) for c in body["data"]]
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return clips[:limit]

    def fetch_window(self, broadcaster_id: str, start: datetime, end: datetime) -> ClipsResult:
        clips, pages = self._collect_clips(broadcaster_id, start, end)
        truncated = len(clips) >= MAX_CLIPS or pages >= HELIX_PAGE_LIMIT
        return ClipsResult(clips=clips[:MAX_CLIPS], truncated=truncated)

    def _collect_clips(self, broadcaster_id: str, start: datetime, end: datetime) -> tuple[list[Clip], int]:
        clips: list[Clip] = []
        cursor = None
        pages = 0
        while len(clips) < MAX_CLIPS:
            params = {
                "broadcaster_id": broadcaster_id,
                "started_at": _rfc3339(start),
                "ended_at": _rfc3339(end),
                "first": 100,
            }
            if cursor:
                params["after"] = cursor
            body = self._get("/clips", params)
            pages += 1
            clips += [_to_clip(c) for c in body["data"]]
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return clips, pages
