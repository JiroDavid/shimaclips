from datetime import date

import numpy as np

from ask import answer
from ask.retrieve import top_k

TODAY = date(2026, 11, 19)
USAGE = {"prompt_tokens": 1, "output_tokens": 1}


def test_top_k_orders_by_cosine_and_applies_threshold():
    mat = np.array([[1, 0], [0, 1], [0.8, 0.6]], dtype=np.float32)
    hits = top_k(np.array([1, 0], dtype=np.float32), ["a", "b", "c"], mat, k=3, min_score=0.5)
    assert [h.clip_id for h in hits] == ["a", "c"]


def test_top_k_empty_index():
    assert top_k(np.array([1.0], dtype=np.float32), [], np.zeros((0, 1), np.float32)) == []


def test_count_answer_comes_from_the_tool_not_the_model(monkeypatch):
    monkeypatch.setattr(answer, "route", lambda q, l: {"tool": "count_clips", "args": {"login": "jay", "when": "this month"}, "usage": USAGE})
    monkeypatch.setattr(answer, "count_clips", lambda conn, **a: {"login": a["login"], "start": a["start"], "end": a["end"], "count": 42})
    r = answer.ask(None, "how many clips this month", "jay", TODAY)
    assert "42" in r["answer"] and r["data"]["start"] == "2026-11-01"


def test_low_confidence_search_does_not_call_the_generator(monkeypatch):
    monkeypatch.setattr(answer, "route", lambda q, l: {"tool": "search_clips", "args": {"query": "x"}, "usage": USAGE})
    monkeypatch.setattr(answer, "search_clips", lambda conn, **a: {"results": [{"id": "c"}], "confident": False})
    monkeypatch.setattr(answer, "_generate", lambda *a: (_ for _ in ()).throw(AssertionError("must not generate")))
    r = answer.ask(None, "something obscure", "jay", TODAY)
    assert r["confident"] is False and r["answer"] == answer.LOW_CONFIDENCE_ANSWER and r["sources"]


def test_bad_date_phrase_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(answer, "route", lambda q, l: {"tool": "count_clips", "args": {"login": "jay", "when": "whenever"}, "usage": USAGE})
    r = answer.ask(None, "how many clips whenever", "jay", TODAY)
    assert r["confident"] is False and "could not" in r["answer"]


def test_no_tool_chosen(monkeypatch):
    monkeypatch.setattr(answer, "route", lambda q, l: {"tool": None, "args": {}, "usage": USAGE})
    assert answer.ask(None, "hello there", "jay", TODAY)["confident"] is False
