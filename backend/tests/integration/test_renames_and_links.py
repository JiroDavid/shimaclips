from .conftest import ask, load_streamer, recent


def test_a_renamed_streamer_is_followed_everywhere_and_old_links_are_repaired(env):
    store = load_streamer(env, "yugi", "5", [("old1", "cooking", 900, recent(2)), ("old2", "chat", 100, recent(3))])
    store.watch_add("yugi", "5")
    env.world.add_streamer("yugi2x", "5", bio="Partner")
    env.world.users.pop("yugi", None)

    r = ask(env, "who is yugi")
    assert r["streamer"]["login"] == "yugi2x" and "yugi2x" in r["answer"]
    assert [c["url"] for c in r["sources"]] == ["https://clips.twitch.tv/old1", "https://clips.twitch.tv/old2"]

    assert store.get_streamer("yugi") is None and store.get_streamer("yugi2x").broadcaster_id == "5"
    watch = env.get("/api/watchlist").json()
    logins = [w["login"] for w in (watch if isinstance(watch, list) else watch.get("entries", watch.get("watchlist", [])))]
    assert "yugi2x" in logins and "yugi" not in logins


def test_the_old_name_still_finds_the_streamer_after_a_rename(env):
    load_streamer(env, "yugi2x", "5", [("c1", "clip", 10, recent(1))])
    env.models.route("count_clips", streamer="yugi", when="last 30 days")
    r = ask(env, "how many clips did yugi get")
    assert r["streamer"]["login"] == "yugi2x" and r["note"] == "I took 'yugi' to mean Yugi2X."
