from .conftest import index_transcripts, load_streamer, recent

JAY = [("j1", "wild night", 500, recent(3)), ("j2", "morning chat", 400, recent(4)), ("j3", "gaming stuff", 300, recent(5))]
SAM = [("s1", "sam boxing day", 900, recent(3))]


def setup(env):
    load_streamer(env, "jay", "1", JAY)
    load_streamer(env, "sam", "2", SAM)
    index_transcripts(env, [
        ("1", "j1", "we watched the boxing match and the fighter won in the ring"),
        ("1", "j2", "just talking about breakfast and coffee"),
        ("1", "j3", "playing chess and losing badly again"),
        ("2", "s1", "boxing boxing boxing all day long"),
    ])


def ask_topic(env, query, streamer="jay"):
    from .conftest import ask
    env.models.route("search_clips", streamer=streamer, query=query)
    return ask(env, f"find clips about {query}")


def test_topic_search_finds_a_clip_by_what_was_said_not_by_its_title(env):
    setup(env)
    r = ask_topic(env, "boxing")
    assert r["confident"] and r["sources"][0]["id"] == "j1"
    assert "boxing" in r["sources"][0]["transcript"]
    assert r["answer"] == env.models.generated and "most viewed" not in r["answer"]


def test_search_never_returns_another_streamers_clips(env):
    setup(env)
    ids = {s["id"] for s in ask_topic(env, "boxing")["sources"]}
    assert "s1" not in ids and ids <= {"j1", "j2", "j3"}


def test_a_word_nobody_said_makes_it_abstain_instead_of_guessing(env):
    setup(env)
    r = ask_topic(env, "poker")
    assert r["confident"] is False and "poker" in r["answer"] and "no transcribed clip mentions" in r["answer"]


def test_the_other_streamers_vocabulary_does_not_count_as_evidence(env):
    setup(env)
    env.models.label = "clips"
    r = ask_topic(env, "boxing", streamer="sam")
    assert r["confident"] and r["sources"][0]["id"] == "s1"
    r2 = ask_topic(env, "chess", streamer="sam")
    assert r2["confident"] is False
