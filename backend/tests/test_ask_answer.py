from datetime import date, datetime, timezone

import numpy as np
import pytest

from ask import answer
from ask.retrieve import top_k
from ask.services import Services
from store import Store
from twitch import ChannelHit, Clip, User

TODAY = date(2026, 11, 19)
USAGE = {"prompt_tokens": 1, "output_tokens": 1}


class FakeTwitch:
    def __init__(self, user=None, hits=()):
        self.user, self.hits = user, list(hits)

    def get_user(self, login):
        return self.user

    def search_channels(self, query, limit=8):
        return self.hits[:limit]

    def get_user_by_id(self, uid):
        return None

    def get_profile(self, uid):
        return {"description": "Hi, mail me at boss@example.com", "broadcaster_type": "partner", "profile_image_url": "",
                "is_live": True, "stream_title": "late night", "game_name": "Chess", "viewer_count": 5}


@pytest.fixture
def svc(tmp_path):
    store = Store(tmp_path / "t.db")
    store.upsert_streamer(User("1", "jay", "Jay", datetime(2020, 1, 1, tzinfo=timezone.utc)))
    store.upsert_clips("1", [
        Clip(f"c{i}", f"https://t/{i}", f"title {i}", "", 100 * i, 30.0, "x", f"2026-11-0{i}T12:00:00Z")
        for i in range(1, 4)
    ])
    return Services(store, None, lambda: FakeTwitch())


def patch_flow(monkeypatch, label="clips", tool="count_clips", args=None):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: (label, USAGE))
    monkeypatch.setattr(
        answer, "route",
        lambda q, d: {"tool": tool, "args": args if args is not None else {"streamer": "jay", "when": "this month"}, "usage": USAGE},
    )


def test_top_k_orders_by_cosine_and_applies_threshold():
    mat = np.array([[1, 0], [0, 1], [0.8, 0.6]], dtype=np.float32)
    hits = top_k(np.array([1, 0], dtype=np.float32), ["a", "b", "c"], mat, k=3, min_score=0.5)
    assert [h.clip_id for h in hits] == ["a", "c"]


def test_top_k_empty_index():
    assert top_k(np.array([1.0], dtype=np.float32), [], np.zeros((0, 1), np.float32)) == []


@pytest.mark.parametrize("label,text", [("off_topic", answer.OFF_TOPIC), ("twitch_other", answer.TWITCH_OTHER)])
def test_refusals_never_reach_the_router(monkeypatch, svc, label, text):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: (label, USAGE))
    monkeypatch.setattr(answer, "route", lambda *a: (_ for _ in ()).throw(AssertionError("must not route")))
    r = answer.ask(svc, "who won the nba", None, TODAY)
    assert r["kind"] == "refusal" and r["answer"] == text and r["confident"] is False


def test_count_comes_from_the_database(monkeypatch, svc):
    patch_flow(monkeypatch)
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "how many clips this month", None, TODAY)
    assert "3 clips" in r["answer"] and r["data"]["start"] == "2026-11-01" and r["streamer"]["login"] == "jay"


def test_partial_period_is_not_reported_as_exact(monkeypatch, svc):
    patch_flow(monkeypatch)
    monkeypatch.setattr(answer, "is_exact", lambda *a: False)
    r = answer.ask(svc, "how many clips this month", None, TODAY)
    assert r["answer"].startswith("At least 3") and "isn't fully loaded" in r["answer"]


def test_default_streamer_is_used_when_question_names_none(monkeypatch, svc):
    patch_flow(monkeypatch, args={"when": "this month"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    assert answer.ask(svc, "how many clips this month", "jay", TODAY)["streamer"]["login"] == "jay"


def test_no_streamer_anywhere_asks_which(monkeypatch, svc):
    patch_flow(monkeypatch, args={"when": "this month"})
    r = answer.ask(svc, "how many clips this month", None, TODAY)
    assert r["kind"] == "needs_streamer" and "Which streamer" in r["answer"]


def test_unknown_streamer_gets_suggestions(monkeypatch, tmp_path):
    hits = [ChannelHit(str(i), f"jaysn{i}", f"Jaysn{i}", "", False) for i in range(3)]
    svc = Services(Store(tmp_path / "t.db"), None, lambda: FakeTwitch(None, hits))
    patch_flow(monkeypatch, args={"streamer": "jasn", "when": "this month"})
    r = answer.ask(svc, "clips of jasn", None, TODAY)
    assert r["kind"] == "unknown_streamer" and "Did you mean" in r["answer"] and len(r["suggestions"]) == 3


def test_new_streamer_is_looked_up_and_stored(monkeypatch, tmp_path):
    user = User("9", "newguy", "NewGuy", datetime(2021, 1, 1, tzinfo=timezone.utc))
    svc = Services(Store(tmp_path / "t.db"), None, lambda: FakeTwitch(user))
    patch_flow(monkeypatch, tool="streamer_info", args={"streamer": "@NewGuy"})
    r = answer.ask(svc, "who is newguy", None, TODAY)
    assert r["streamer"]["login"] == "newguy" and "2021-01-01" in r["answer"]
    assert svc.store.get_streamer("newguy") is not None


def test_monthly_tool_returns_months(monkeypatch, svc):
    patch_flow(monkeypatch, tool="top_clips_by_month", args={"streamer": "jay", "year": 2026, "per_month": 10})
    months = [{"month": "2026-01", "clips": [{"id": "a"}], "exact": True}, {"month": "2026-02", "clips": [], "exact": False}]
    monkeypatch.setattr(answer, "top_by_month", lambda *a: months)
    r = answer.ask(svc, "rewind", None, TODAY)
    assert r["months"] == months and "2026" in r["answer"] and "not fully loaded" in r["after"]


def test_future_year_rejected(monkeypatch, svc):
    patch_flow(monkeypatch, tool="top_clips_by_month", args={"streamer": "jay", "year": 2031})
    r = answer.ask(svc, "rewind", None, TODAY)
    assert r["confident"] is False and "year must be" in r["answer"]


def test_search_without_transcripts_says_so(monkeypatch, svc):
    patch_flow(monkeypatch, tool="search_clips", args={"streamer": "jay", "query": "chess"})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: 0)
    r = answer.ask(svc, "clips about chess", None, TODAY)
    assert "haven't transcribed" in r["answer"] and r["confident"] is False


def test_low_confidence_search_does_not_call_the_generator(monkeypatch, svc):
    patch_flow(monkeypatch, tool="search_clips", args={"streamer": "jay", "query": "poker"})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: 5)
    monkeypatch.setattr(answer, "search_clips", lambda conn, *a, **k: {"results": [{"id": "c"}], "confident": False, "unseen_words": ["poker"]})
    monkeypatch.setattr(answer, "_generate", lambda *a: (_ for _ in ()).throw(AssertionError("must not generate")))
    r = answer.ask(svc, "clips about poker", None, TODAY)
    assert r["confident"] is False and "poker" in r["answer"] and r["sources"]


def test_bad_date_phrase_is_reported_not_raised(monkeypatch, svc):
    patch_flow(monkeypatch, args={"streamer": "jay", "when": "whenever"})
    r = answer.ask(svc, "how many clips whenever", None, TODAY)
    assert r["confident"] is False and "could not" in r["answer"]


def test_no_tool_chosen_falls_back_to_topic_search(monkeypatch, svc):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: ("clips", USAGE))
    monkeypatch.setattr(answer, "route", lambda q, d: {"tool": None, "args": {}, "usage": USAGE})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: 0)
    r = answer.ask(svc, "clips about someone's birthday", "jay", TODAY)
    assert r["tool"] == "search_clips" and "fallback" in r and "haven't transcribed" in r["answer"]


def test_no_tool_and_no_streamer_asks_which(monkeypatch, svc):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: ("clips", USAGE))
    monkeypatch.setattr(answer, "route", lambda q, d: {"tool": None, "args": {}, "usage": USAGE})
    assert answer.ask(svc, "hello there friend", None, TODAY)["kind"] == "needs_streamer"


def test_known_streamer_in_the_question_beats_a_missing_one(monkeypatch, svc):
    patch_flow(monkeypatch, args={"when": "this month"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "how many clips did jay get this month", None, TODAY)
    assert r["streamer"]["login"] == "jay"


def test_two_streamers_in_one_name_uses_the_first_real_one(monkeypatch, svc):
    patch_flow(monkeypatch, args={"streamer": "nobodyhere jay", "when": "this month"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "how many clips this month", None, TODAY)
    assert r["streamer"]["login"] == "jay" and "one streamer at a time" in r["note"]


def test_suggestions_are_ranked_by_closeness_to_what_was_typed():
    from ask.streamers import rank_suggestions
    hits = [ChannelHit(str(i), n, n, "", False) for i, n in enumerate(["jasontheween_yujin", "jasontheween", "jasontheweens"])]
    assert [h.login for h in rank_suggestions("jasonthewen", hits, 2)] == ["jasontheween", "jasontheweens"]


def test_glued_names_fall_back_to_a_known_streamer_in_the_question(monkeypatch, svc):
    patch_flow(monkeypatch, args={"streamer": "jaystableronaldo", "when": "this month"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "who is burger? jay stableronaldo", None, TODAY)
    assert r["kind"] == "answer" and r["streamer"]["login"] == "jay"


def test_search_answer_and_date_note_are_separate_fields(monkeypatch, svc):
    patch_flow(monkeypatch, tool="search_clips", args={"streamer": "jay", "query": "boxing"})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: 5)
    results = [{"id": "c", "title": "t", "url": "u", "view_count": 1, "created_at": "2026-02-03T00:00:00Z", "transcript": "x"}]
    monkeypatch.setattr(answer, "search_clips", lambda conn, *a, **k: {"results": results, "confident": True, "unseen_words": []})
    monkeypatch.setattr(answer, "_generate", lambda *a: ("He talks about boxing [1].", USAGE))
    r = answer.ask(svc, "boxing", None, TODAY)
    assert r["answer"] == "He talks about boxing [1]." and "2026-02-03" in r["after"]


def test_empty_period_says_no_clips_instead_of_top_zero(monkeypatch, svc):
    patch_flow(monkeypatch, tool="top_clips", args={"streamer": "jay", "when": "2025", "limit": 5})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "top clips 2025", None, TODAY)
    assert "couldn't find any clips" in r["answer"] and r["sources"] == []


def test_newest_on_a_partial_period_falls_back_to_views_and_says_so(monkeypatch, svc):
    patch_flow(monkeypatch, tool="top_clips", args={"streamer": "jay", "when": "this month", "limit": 2, "sort": "newest"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: False)
    r = answer.ask(svc, "newest clips this month", None, TODAY)
    assert r["answer"].startswith("Here are the top 2") and "sorted by views" in r["after"]
    assert [c["view_count"] for c in r["sources"]] == [300, 200]


def test_newest_on_an_exact_period_is_honoured(monkeypatch, svc):
    patch_flow(monkeypatch, tool="top_clips", args={"streamer": "jay", "when": "this month", "limit": 2, "sort": "newest"})
    monkeypatch.setattr(answer, "is_exact", lambda *a: True)
    r = answer.ask(svc, "newest clips this month", None, TODAY)
    assert r["answer"].startswith("Here are the newest 2") and [c["id"] for c in r["sources"]] == ["c3", "c2"]


def test_who_is_a_known_streamer_uses_twitch_profile_then_clips_without_calling_the_router(monkeypatch, svc):
    monkeypatch.setattr(answer, "classify", lambda q, d=None: ("clips", USAGE))
    monkeypatch.setattr(answer, "route", lambda *a: (_ for _ in ()).throw(AssertionError("must not route")))
    r = answer.ask(svc, "hey who is jay?", None, TODAY)
    assert r["tool"] == "streamer_info" and "a Twitch Partner" in r["answer"] and "live right now playing Chess" in r["answer"]
    assert "boss@example.com" not in r["answer"] and "[email hidden]" in r["answer"]
    assert len(r["sources"]) == 3 and "most viewed clips" in r["after"]


def test_who_is_something_that_is_not_a_streamer_is_searched_in_the_clips(monkeypatch, svc):
    patch_flow(monkeypatch, tool="streamer_info", args={"streamer": "burger"})
    monkeypatch.setattr(answer, "_transcribed", lambda *a: 0)
    r = answer.ask(svc, "who is burger", "jay", TODAY)
    assert r["tool"] == "search_clips" and "fallback" in r and r["streamer"]["login"] == "jay"


def test_who_is_target_only_matches_known_streamers(svc):
    from ask.streamers import who_is_target
    assert who_is_target(svc, "who is jay", None) == "jay"
    assert who_is_target(svc, "Tell me about @Jay!", None) == "jay"
    assert who_is_target(svc, "who is burger", None) is None
    assert who_is_target(svc, "who is jay and why does he clip so much", None) is None
