from ask.web import Source, WebUnavailable
from .conftest import CREATED, ask, load_streamer, recent

ROWS = [(f"c{i}", f"clip {i}", 100 * (i + 1), recent(i + 1)) for i in range(6)]


def test_a_count_question_is_answered_from_the_database_and_saved_to_history(env):
    load_streamer(env, "jay", "1", ROWS)
    env.models.route("count_clips", streamer="jay", when="last 30 days")
    r = ask(env, "how many clips did jay get lately")
    assert r["kind"] == "answer" and r["tool"] == "count_clips" and r["data"]["count"] == 6
    assert r["streamer"] == {"login": "jay", "display_name": "Jay"}
    listed = env.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [r["conversation_id"]]
    assert env.get(f"/api/conversations/{r['conversation_id']}").json()["turns"][0]["result"]["data"]["count"] == 6


def test_top_clips_for_a_new_streamer_are_fetched_live_stored_and_linked_by_id(env):
    env.world.add_streamer("sam", "2")
    for i, views in enumerate([50, 900, 300, 700]):
        env.world.make_clip("2", f"s{i}", f"sam clip {i}", views, i + 1)
    env.models.route("top_clips", streamer="sam", when="last 30 days", limit=3)
    r = ask(env, "top 3 clips for sam")
    assert [c["view_count"] for c in r["sources"]] == [900, 700, 300]
    assert all(c["url"] == f"https://clips.twitch.tv/{c['id']}" for c in r["sources"])
    assert env.main.get_store().get_streamer("sam") is not None
    assert env.world.calls.count("get_user:sam") == 1


def test_who_is_shows_the_profile_then_clips_without_asking_the_model(env):
    env.world.add_streamer("jay", "1", bio="Hi, mail me at boss@example.com", live=True)
    load_streamer(env, "jay", "1", ROWS)
    r = ask(env, "who is jay")
    assert env.models.router_calls == 0 and r["tool"] == "streamer_info"
    assert "a Twitch Partner" in r["answer"] and "live right now playing Chess" in r["answer"]
    assert "boss@example.com" not in r["answer"] and "[email hidden]" in r["answer"]
    assert len(r["sources"]) == 5 and "most viewed clips" in r["after"]


def test_a_misspelt_streamer_gets_suggestions_and_nothing_is_stored(env):
    env.world.add_streamer("jayden", "7")
    env.world.add_streamer("jaylen", "8")
    env.models.route("top_clips", streamer="jayz", when="last 30 days")
    r = ask(env, "top clips for jayz")
    assert r["kind"] == "unknown_streamer" and {s["login"] for s in r["suggestions"]} == {"jayden", "jaylen"}
    assert env.main.get_store().get_streamer("jayz") is None


def test_a_nickname_means_the_known_streamer_not_an_unrelated_twitch_channel(env):
    load_streamer(env, "jasontheween", "10", ROWS)
    env.world.add_streamer("jason", "99")
    env.models.route("count_clips", streamer="jason", when="last 30 days")
    r = ask(env, "how many clips did jason get lately")
    assert r["streamer"]["login"] == "jasontheween" and r["note"] == "I took 'jason' to mean Jasontheween."
    assert "get_user:jason" not in env.world.calls and env.main.get_store().get_streamer("jason") is None


def test_off_topic_questions_are_refused_before_any_tool_runs(env):
    env.models.label = "off_topic"
    r = ask(env, "what is the capital of japan")
    assert r["kind"] == "refusal" and env.models.router_calls == 0 and r["sources"] == []


def stub_web(monkeypatch, calls):
    def search(q):
        calls.append(q)
        return [{"href": "https://7tv.app/", "title": "7TV", "body": "7TV is a browser extension for emotes."}]

    monkeypatch.setattr("ask.web.search", search)
    monkeypatch.setattr("ask.web.fetch_text", lambda url: "7TV is a third-party emote extension for Twitch chat.")
    monkeypatch.setattr("ask.web_answer._generate", lambda q, s: ("7TV is a browser extension [1].", {"prompt_tokens": 9, "output_tokens": 9}))


def test_a_general_twitch_question_is_answered_from_the_web_with_sources_and_cached(env, monkeypatch):
    calls = []
    stub_web(monkeypatch, calls)
    env.models.label = "twitch_other"
    first = ask(env, "what are 7tv emotes")
    again = ask(env, "What are 7TV emotes?")
    assert first["confident"] and first["web_sources"][0]["domain"] == "7tv.app" and "[1]" in first["answer"]
    assert first["web"]["cached"] is False and again["web"]["cached"] is True and len(calls) == 1
    assert env.models.router_calls == 0


def test_when_the_web_is_down_the_answer_says_so_and_nothing_is_invented(env, monkeypatch):
    monkeypatch.setattr("ask.web.search", lambda q: (_ for _ in ()).throw(WebUnavailable("down")))
    env.models.label = "twitch_other"
    r = ask(env, "did anyone win a streamer award")
    assert "couldn't reach the web" in r["answer"] and r["web_sources"] == [] and r["confident"] is False


def test_a_web_answer_about_a_known_streamer_is_followed_by_their_clips(env, monkeypatch):
    stub_web(monkeypatch, [])
    load_streamer(env, "jay", "1", ROWS)
    env.models.label = "twitch_other"
    r = ask(env, "how old is jay")
    assert r["web_sources"] and r["streamer"]["login"] == "jay" and len(r["sources"]) == 5
