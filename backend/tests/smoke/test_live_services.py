import os
import sqlite3
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pytest
from dotenv import load_dotenv

pytestmark = pytest.mark.smoke
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DB = ROOT / "shimaclips.db"
OLLAMA = "http://localhost:11434"


def test_ollama_is_running_with_the_models_the_app_needs():
    names = {m["name"] for m in httpx.get(f"{OLLAMA}/api/tags", timeout=10).json()["models"]}
    assert any(n.startswith("llama3.1:8b") for n in names) and any(n.startswith("nomic-embed-text") for n in names)


def test_the_topic_guard_separates_clip_questions_from_off_topic_ones():
    from ask.guard import classify
    assert classify("what is the capital of france")[0] == "off_topic"
    assert classify("top 10 clips for jasontheween this month")[0] == "clips"
    assert classify("what are 7tv emotes")[0] == "twitch_other"


def test_embeddings_are_unit_length_vectors_of_the_expected_size():
    from ask.embed import embed_query
    v = embed_query("a streamer talking about boxing")
    assert v.shape == (768,) and abs(float(np.linalg.norm(v)) - 1.0) < 1e-3


def test_the_router_picks_a_tool_and_copies_the_date_words():
    from ask.router import route
    r = route("how many clips did jasontheween get last month", None)
    assert r["tool"] == "count_clips" and "last month" in r["args"]["when"].lower()


def test_twitch_credentials_work_and_resolve_a_real_streamer():
    from twitch import TwitchClient
    user = TwitchClient(os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"]).get_user("jasontheween")
    assert user is not None and user.login == "jasontheween" and user.created_at.year == 2015


def test_web_search_returns_public_results():
    from ask.web import search
    results = search("what are 7tv emotes")
    assert results and all(r["href"].startswith("http") for r in results)


@pytest.mark.skipif(not DB.exists(), reason="needs the local clip database")
def test_a_stored_clip_still_resolves_through_the_download_extractor():
    import yt_dlp
    clip_id = sqlite3.connect(f"file:{DB}?mode=ro", uri=True).execute("SELECT id FROM clips ORDER BY view_count DESC LIMIT 1").fetchone()[0]
    with yt_dlp.YoutubeDL({"quiet": True, "allowed_extractors": ["twitch:clips"]}) as ydl:
        info = ydl.extract_info(f"https://clips.twitch.tv/{clip_id}", download=False)
    assert info.get("title") and info.get("duration", 0) > 0


def test_speech_to_text_loads_and_runs_on_audio():
    from ask import transcribe
    model = transcribe._load_model()
    segments, _ = model.transcribe(np.zeros(16000, dtype=np.float32), vad_filter=True)
    assert list(segments) == []
    assert model.model.device in ("cuda", "cpu")


@pytest.mark.skipif(not DB.exists(), reason="needs the local clip database")
def test_the_whole_pipeline_answers_real_questions_end_to_end():
    import main
    from ask.answer import ask
    from ask.services import Services
    svc = Services(main.get_store(), main.get_live(), main.get_twitch)
    top = ask(svc, "top 3 clips for jasontheween this year", None, date.today())
    assert top["tool"] == "top_clips" and len(top["sources"]) == 3
    assert all(c["url"].startswith("https://clips.twitch.tv/") for c in top["sources"])
    who = ask(svc, "who is jasontheween", None, date.today())
    assert who["tool"] == "streamer_info" and "Twitch" in who["answer"] and len(who["sources"]) == 5
    topic = ask(svc, "find clips where jasontheween talks about boxing", None, date.today())
    assert topic["tool"] == "search_clips" and topic["sources"]
    refused = ask(svc, "how do i fix my laptop wifi", None, date.today())
    assert refused["kind"] == "refusal"
