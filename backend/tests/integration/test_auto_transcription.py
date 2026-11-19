import time
from pathlib import Path

from .conftest import ask, recent

TEXTS = {"n0": "a long talk about boxing and training", "n1": "cooking pasta for dinner", "n2": "more cooking and pasta", "n3": "gaming all night"}


def fake_pipeline(monkeypatch):
    def download(clip_id, url, tmp):
        path = Path(tmp) / f"{clip_id}.mp4"
        path.write_bytes(b"video")
        return clip_id, path, 0.01, None

    monkeypatch.setattr("ask.transcribe._download", download)
    monkeypatch.setattr("ask.transcribe.transcribe_path", lambda p: (TEXTS[p.stem], 0.01))


def wait_for(env, login, state, timeout=20.0):
    end = time.time() + timeout
    seen = []
    while time.time() < end:
        s = env.get(f"/api/streamers/{login}/transcribe").json()
        seen.append(s["state"])
        if s["state"] == state:
            return s, seen
        assert s["state"] != "error", s
        time.sleep(0.1)
    raise AssertionError(f"never reached {state}: {seen[-5:]}")


def test_a_topic_question_about_an_untranscribed_streamer_transcribes_them_then_works(env, monkeypatch):
    fake_pipeline(monkeypatch)
    env.world.add_streamer("newbie", "9")
    for i in range(4):
        env.world.make_clip("9", f"n{i}", f"newbie clip {i}", 100 * (i + 1), i + 2)
    env.models.route("search_clips", streamer="newbie", query="boxing")

    first = ask(env, "find clips where newbie talks about boxing")
    assert first["transcription"]["state"] in ("queued", "finding", "transcribing", "indexing", "done")
    assert "started now" in first["answer"] and first["confident"] is False

    status, seen = wait_for(env, "newbie", "done")
    assert status["processed"] == status["total"] == 4 and status["transcribed"] == 4

    second = ask(env, "find clips where newbie talks about boxing")
    assert second["confident"] and second["sources"][0]["id"] == "n0"
    assert "transcription" not in second
    work = env.tmp / "work"
    assert not [p for p in work.glob("shimaclips_tr_*") if p.is_dir() and any(p.iterdir())]


def test_asking_again_while_it_runs_does_not_start_a_second_job(env, monkeypatch):
    fake_pipeline(monkeypatch)
    env.world.add_streamer("newbie", "9")
    env.world.make_clip("9", "n0", "one clip", 10, 2)
    env.models.route("search_clips", streamer="newbie", query="boxing")
    ask(env, "boxing please")
    ask(env, "boxing please again")
    wait_for(env, "newbie", "done")
    assert env.world.calls.count("get_user:newbie") == 1


def test_the_progress_endpoint_404s_for_an_unknown_streamer_and_can_be_switched_off(env, monkeypatch):
    assert env.get("/api/streamers/nobody/transcribe").status_code == 404
    env.world.add_streamer("newbie", "9")
    monkeypatch.setenv("SHIMACLIPS_TRANSCRIBE", "0")
    env.models.route("search_clips", streamer="newbie", query="boxing")
    r = ask(env, "boxing please")
    assert "transcription" not in r and "can't search by topic" in r["answer"]
