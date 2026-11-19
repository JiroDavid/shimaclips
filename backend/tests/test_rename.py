from datetime import datetime, timezone

from ask import streamers
from ask.services import Services
from store import Store
from twitch import Clip, User, _to_clip, clip_url

CREATED = datetime(2023, 7, 24, tzinfo=timezone.utc)


def user(login, uid="9"):
    return User(uid, login, login.title(), CREATED)


def test_clip_links_are_built_from_the_id_so_renames_cannot_break_them():
    raw = {"id": "AbcDef-123", "url": "https://www.twitch.tv/oldname/clip/AbcDef-123", "title": "t", "thumbnail_url": "",
           "view_count": 1, "duration": 5.0, "creator_name": "x", "created_at": "2026-01-01T00:00:00Z"}
    assert _to_clip(raw).url == "https://clips.twitch.tv/AbcDef-123" == clip_url("AbcDef-123")


def test_stored_old_style_links_are_served_in_the_new_form(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(user("yugi"))
    store.upsert_clips("9", [Clip("C1", "https://www.twitch.tv/yugi/clip/C1", "t", "", 5, 5.0, "x", "2026-01-01T00:00:00Z")])
    assert store.top_clips("9", None, None, 5, 0)[0][0].url == "https://clips.twitch.tv/C1"


def test_rename_updates_the_streamer_and_the_watchlist_entry(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(user("yugi"))
    store.watch_add("yugi", "9")
    store.upsert_streamer(user("yugi2x"))
    assert store.get_streamer("yugi2x").broadcaster_id == "9" and store.get_streamer("yugi") is None
    assert [e.login for e in store.watch_list() if e.broadcaster_id == "9"] == ["yugi2x"]


def test_rename_does_not_duplicate_when_the_new_name_is_already_watched(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(user("yugi"))
    store.watch_add("yugi", "9")
    store.watch_add("yugi2x", "9")
    store.upsert_streamer(user("yugi2x"))
    assert [e.login for e in store.watch_list() if e.broadcaster_id == "9"] == ["yugi2x"]


class FakeTwitch:
    def __init__(self, current):
        self.current, self.calls = current, 0

    def get_user_by_id(self, uid):
        self.calls += 1
        return self.current


def test_resolving_a_known_streamer_picks_up_a_new_name_and_checks_only_hourly(tmp_path):
    streamers._checked.clear()
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(user("yugi"))
    fake = FakeTwitch(user("yugi2x"))
    svc = Services(store, None, lambda: fake)
    assert streamers.resolve(svc, "yugi")["streamer"].login == "yugi2x"
    streamers.resolve(svc, "yugi2x")
    assert fake.calls == 1


def make_known(tmp_path, *logins):
    store = Store(tmp_path / "t.db")
    for i, login in enumerate(logins):
        store.upsert_streamer(user(login, str(i + 1)))
    return Services(store, None, None)


def test_a_nickname_resolves_to_the_one_known_streamer_it_starts(tmp_path):
    svc = make_known(tmp_path, "jasontheween", "ludwig")
    res = streamers.resolve(svc, "jason")
    assert res["status"] == "ok" and res["streamer"].login == "jasontheween" and res["alias_of"] == "jason"


def test_an_ambiguous_or_too_short_nickname_is_not_guessed(tmp_path):
    svc = make_known(tmp_path, "jasontheween", "jasonbourne")
    assert streamers.resolve(svc, "jason")["status"] == "unknown"
    assert streamers.resolve(make_known(tmp_path / "x" if False else tmp_path, "ludwig"), "lud")["status"] == "unknown"


def test_an_old_name_after_a_rename_still_finds_the_streamer(tmp_path):
    svc = make_known(tmp_path, "yugi2x")
    assert streamers.resolve(svc, "yugi")["streamer"].login == "yugi2x"
