import re
from difflib import SequenceMatcher

from ask.services import Services
from store import Streamer
from twitch import TwitchError

_STRIP = re.compile(r"[^a-z0-9_]")
SUGGESTIONS = 5


def clean_login(name: str) -> str:
    return _STRIP.sub("", name.strip().lstrip("@").lower())


def split_names(name: str) -> list[str]:
    parts = [p for p in re.split(r"[,&/]|\s+and\s+|\s+", name.strip()) if clean_login(p)]
    return parts or [name]


def rank_suggestions(typed: str, hits: list, limit: int) -> list:
    wanted = clean_login(typed)
    return sorted(
        hits,
        key=lambda h: (SequenceMatcher(None, wanted, h.login.lower()).ratio(), h.is_live),
        reverse=True,
    )[:limit]


def all_mentioned(svc: Services, question: str) -> list[str]:
    known = set(svc.store.known_logins())
    found: list[str] = []
    for word in re.findall(r"[a-z0-9_]+", question.lower()):
        if word in known and word not in found:
            found.append(word)
    return found


def mentioned(svc: Services, question: str) -> str | None:
    found = all_mentioned(svc, question)
    return found[0] if found else None


def resolve(svc: Services, name: str) -> dict:
    login = clean_login(name)
    if not 1 <= len(login) <= 25:
        return {"status": "unknown", "name": name, "suggestions": []}
    known = svc.store.get_streamer(login)
    if known is not None:
        return {"status": "ok", "streamer": known}
    if svc.twitch is None:
        return {"status": "unknown", "name": name, "suggestions": []}
    try:
        client = svc.twitch()
        user = client.get_user(login)
        if user is not None:
            svc.store.upsert_streamer(user)
            return {"status": "ok", "streamer": svc.store.get_streamer(user.login)}
        hits = rank_suggestions(login, client.search_channels(login, limit=20), SUGGESTIONS)
    except TwitchError as e:
        return {"status": "error", "message": str(e)}
    return {
        "status": "unknown",
        "name": name,
        "suggestions": [
            {"login": h.login, "display_name": h.display_name, "avatar_url": h.thumbnail_url, "is_live": h.is_live}
            for h in hits
        ],
    }


def public(streamer: Streamer) -> dict:
    return {"login": streamer.login, "display_name": streamer.display_name}
