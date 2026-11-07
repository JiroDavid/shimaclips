import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.twitch.tv/helix"
MAX_CLIPS = 3000


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
class ClipsResult:
    clips: list[Clip]
    truncated: bool


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retry_after(r: httpx.Response) -> float:
    try:
        return max(float(r.headers.get("Retry-After", 1)), 0)
    except ValueError:
        return 1


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15)
        self._token: str | None = None
        self._expires = 0.0
        self._token_lock = threading.Lock()

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

    def _get(self, path: str, params: dict) -> dict:
        if not self._token or time.time() >= self._expires:
            self._fetch_token()
        refreshed = False
        for attempt in range(3):
            token = self._token
            r = self._http.get(f"{API_URL}{path}", params=params, headers={
                "Client-Id": self._client_id,
                "Authorization": f"Bearer {token}",
            })
            if r.status_code == 401 and not refreshed:
                refreshed = True
                self._fetch_token(stale=token)
                continue
            if r.status_code == 429 and attempt < 2:
                time.sleep(_retry_after(r))
                continue
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

    def fetch_window(self, broadcaster_id: str, start: datetime, end: datetime) -> ClipsResult:
        clips = self._collect_clips(broadcaster_id, start, end)[:MAX_CLIPS]
        return ClipsResult(clips=clips, truncated=len(clips) >= MAX_CLIPS)

    def _collect_clips(self, broadcaster_id: str, start: datetime, end: datetime) -> list[Clip]:
        clips: list[Clip] = []
        cursor = None
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
            clips += [
                Clip(
                    id=c["id"], url=c["url"], title=c["title"], thumbnail_url=c["thumbnail_url"],
                    view_count=c["view_count"], duration=c["duration"],
                    creator_name=c["creator_name"], created_at=c["created_at"],
                )
                for c in body["data"]
            ]
            cursor = body.get("pagination", {}).get("cursor")
            if not cursor:
                break
        return clips
