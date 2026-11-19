import sqlite3

from ask.keyword import fuse, keyword_search, match_query, rebuild
from ask.retrieve import Hit


def make():
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE clips (id TEXT, title TEXT);"
        "CREATE TABLE transcripts (clip_id TEXT, text TEXT);"
        "INSERT INTO clips VALUES ('a', 'island day one'), ('b', 'chess time'), ('c', 'funny');"
        "INSERT INTO transcripts VALUES ('a', 'we landed on the island today'), "
        "('b', 'I am bad at chess honestly'), ('c', 'chess on the island');"
    )
    rebuild(c)
    return c


def test_stopwords_and_quoting():
    assert match_query("Find clips where he talks about chess") == '"chess"'
    assert match_query("the a of") is None
    assert match_query('say "hi" AND NEAR(') == '"say" OR "hi" OR "near"'


def test_keyword_search_finds_and_ranks():
    c = make()
    ids = [h.clip_id for h in keyword_search(c, "chess", k=5)]
    assert set(ids) == {"b", "c"}
    assert [h.clip_id for h in keyword_search(c, "island chess", k=1)] == ["c"]


def test_no_terms_returns_nothing():
    assert keyword_search(make(), "when did he do it") == []


def test_fuse_rewards_agreement():
    a = [Hit("x", 1), Hit("y", 0.9)]
    b = [Hit("y", 5), Hit("z", 4)]
    assert fuse([a, b], k=3)[0].clip_id == "y"
