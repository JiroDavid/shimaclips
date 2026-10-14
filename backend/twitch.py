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


def _rfc3339(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def top_clips(clips: list[Clip], n: int) -> list[Clip]:
    return sorted(clips, key=lambda c: c.view_count, reverse=True)[:n]


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None):
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15)
        self._token: str | None = None
        self._expires = 0.0

    def _fetch_token(self) -> None:
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
        for attempt in range(2):
            r = self._http.get(f"{API_URL}{path}", params=params, headers={
                "Client-Id": self._client_id,
                "Authorization": f"Bearer {self._token}",
            })
            if r.status_code == 401 and attempt == 0:
                self._fetch_token()
                continue
            break
        if r.status_code != 200:
            raise TwitchError(f"Twitch API error ({r.status_code})")
        return r.json()

    def get_user_id(self, login: str) -> str | None:
        login = login.strip().lstrip("@").lower()
        data = self._get("/users", {"login": login})["data"]
        return data[0]["id"] if data else None

    def get_clips(self, broadcaster_id: str, start: datetime, end: datetime) -> list[Clip]:
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
        return clips[:MAX_CLIPS]
