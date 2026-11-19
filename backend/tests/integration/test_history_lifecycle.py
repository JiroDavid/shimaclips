from .conftest import ask, load_streamer, recent

ROWS = [(f"c{i}", f"clip {i}", 10 * (i + 1), recent(i + 1)) for i in range(4)]


def test_chats_can_be_continued_reopened_renamed_and_deleted(env):
    load_streamer(env, "jay", "1", ROWS)
    env.models.route("top_clips", streamer="jay", when="last 30 days", limit=2)
    a1 = ask(env, "top 2 clips for jay")
    a2 = ask(env, "and again please", conversation_id=a1["conversation_id"])
    b1 = ask(env, "a different chat about jay")
    assert a2["conversation_id"] == a1["conversation_id"] != b1["conversation_id"]

    listed = env.get("/api/conversations").json()["conversations"]
    assert [c["id"] for c in listed] == [b1["conversation_id"], a1["conversation_id"]]

    reopened = env.get(f"/api/conversations/{a1['conversation_id']}").json()
    assert [t["question"] for t in reopened["turns"]] == ["top 2 clips for jay", "and again please"]
    assert reopened["turns"][0]["result"]["sources"] == a1["sources"]

    assert env.put(f"/api/conversations/{a1['conversation_id']}", json={"title": "Jay rewind"}).status_code == 200
    assert env.get(f"/api/conversations/{a1['conversation_id']}").json()["title"] == "Jay rewind"
    assert env.delete(f"/api/conversations/{b1['conversation_id']}").status_code == 200
    assert env.get(f"/api/conversations/{b1['conversation_id']}").status_code == 404
    assert [c["id"] for c in env.get("/api/conversations").json()["conversations"]] == [a1["conversation_id"]]


def test_history_survives_an_app_restart(env):
    load_streamer(env, "jay", "1", ROWS)
    env.models.route("count_clips", streamer="jay", when="last 30 days")
    cid = ask(env, "how many clips")["conversation_id"]
    for name in ("_store", "_live", "_manager", "_transcriber"):
        setattr(env.main, name, None)
    assert [c["id"] for c in env.get("/api/conversations").json()["conversations"]] == [cid]
