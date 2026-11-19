import json
import re
import sys
import time
from datetime import date
from pathlib import Path

from ask.answer import ask
from ask.services import Services
from ask.tools import open_readonly
from store import Store

HERE = Path(__file__).parent
DB = HERE.parent.parent / "shimaclips.db"
TODAY = date(2026, 11, 19)


def bid(conn, login):
    return conn.execute("SELECT broadcaster_id FROM streamers WHERE login = ?", (login,)).fetchone()[0]


def clip_text(conn, clip_id):
    row = conn.execute(
        "SELECT k.title, COALESCE(t.text, '') FROM clips k LEFT JOIN transcripts t ON t.clip_id = k.id WHERE k.id = ?", (clip_id,)
    ).fetchone()
    return f"{row[0]} {row[1]}".lower() if row else ""


def sql_top_views(conn, login, start, end, limit):
    return [r[0] for r in conn.execute(
        "SELECT view_count FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ? ORDER BY view_count DESC LIMIT ?",
        (bid(conn, login), start, end, limit))]


def sql_count(conn, login, start, end):
    return conn.execute("SELECT COUNT(*) FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ?",
                        (bid(conn, login), start, end)).fetchone()[0]


def cited_ok(r):
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", r["answer"])}
    return bool(cited) and cited <= {s["n"] for s in r["web_sources"]}


def check_top(login, start, end, limit):
    def f(r, conn):
        got = [s["view_count"] for s in r["sources"]]
        return r["tool"] == "top_clips" and (r["streamer"] or {}).get("login") == login and got == sql_top_views(conn, login, start, end, limit), \
            f"tool={r['tool']} range={(r.get('data') or {}).get('start')}..{(r.get('data') or {}).get('end')} got {len(got)} clips"
    return f


def check_topic(login, pattern, k=5):
    rx = re.compile(pattern, re.I)

    def f(r, conn):
        hits = sum(bool(rx.search(clip_text(conn, s["id"]))) for s in r["sources"][:k])
        exists = conn.execute(
            "SELECT 1 FROM transcripts t JOIN clips c ON c.id = t.clip_id WHERE c.broadcaster_id = ? AND (lower(t.text) REGEXP ? OR lower(c.title) REGEXP ?) LIMIT 1",
            (bid(conn, login), pattern, pattern)).fetchone() is not None
        if not exists:
            return (not r["confident"]), "no clip in the library matches, so it should abstain"
        return r["tool"] == "search_clips" and hits >= 1, f"{hits} of the top {k} clips match /{pattern}/"
    return f


def check_web(keywords):
    def f(r, conn):
        if r["web_sources"] == [] or r.get("topic") != "twitch_other":
            return False, f"not routed to the web (topic={r.get('topic')}, kind={r['kind']})"
        if not r["confident"]:
            return True, "honest 'could not verify'"
        return cited_ok(r) and any(k in r["answer"].lower() for k in keywords), "cited answer with an expected term"
    return f


CASES = [
    ("h01", "show me marlon's top 5 clips from last month", check_top("marlon", "2026-10-01", "2026-11-01", 5)),
    ("h02", "how many clips did ludwig get in 2023", lambda r, c: (r["tool"] == "count_clips" and (r.get("data") or {}).get("count") == sql_count(c, "ludwig", "2023-01-01", "2024-01-01"),
                                                                    f"tool={r['tool']} count={(r.get('data') or {}).get('count')} sql={sql_count(c, 'ludwig', '2023-01-01', '2024-01-01')}")),
    ("h03", "arky's most viewed clips of this year", check_top("arky", "2026-01-01", "2027-01-01", 10)),
    ("h04", "what's the total number of views on stableronaldo's clips in September",
     lambda r, c: (r["tool"] == "view_stats" and (r.get("data") or {}).get("total") == c.execute(
         "SELECT COALESCE(SUM(view_count),0) FROM clips WHERE broadcaster_id = ? AND created_at >= '2026-09-01' AND created_at < '2026-10-01'", (bid(c, "stableronaldo"),)).fetchone()[0],
                   f"tool={r['tool']} total={(r.get('data') or {}).get('total')}")),
    ("h05", "who is yugi", lambda r, c: (r["kind"] == "unknown_streamer" and any(s["login"] == "yugi2x" for s in r["suggestions"]) or (r["streamer"] or {}).get("login") == "yugi2x",
                                          f"kind={r['kind']} suggestions={[s['login'] for s in r['suggestions']][:3]}")),
    ("h06", "tell me about marlon", lambda r, c: (r["tool"] == "streamer_info" and (r["streamer"] or {}).get("login") == "marlon" and len(r["sources"]) > 0, f"tool={r['tool']} clips={len(r['sources'])}")),
    ("h07", "what is a twitch affiliate and how is it different from a partner", check_web(["affiliate"])),
    ("h08", "is the streamer awards still happening this year", check_web(["award"])),
    ("h09", "how do i add 7tv to my twitch chat", check_web(["7tv", "extension", "install"])),
    ("h10", "find clips where jasontheween talks about gta", check_topic("jasontheween", r"\bgta\b")),
    ("h11", "when did jason go to nyc", check_topic("jasontheween", r"\bnyc\b|new york")),
    ("h12", "clips of arky cooking", check_topic("arky", r"\bcook")),
    ("h13", "what's the capital of japan", lambda r, c: (r["kind"] == "refusal", f"kind={r['kind']}")),
    ("h14", "how do i fix my laptop wifi", lambda r, c: (r["kind"] == "refusal", f"kind={r['kind']}")),
    ("h15", "show me clips about poker from arky", lambda r, c: (not r["confident"], f"confident={r['confident']}")),
    ("h16", "top 3 clips from jasontheween on christmas day 2025",
     lambda r, c: ((r.get("data") or {}).get("start") == "2025-12-25" or not r["confident"], f"range={(r.get('data') or {}).get('start')} confident={r['confident']}: {r['answer'][:80]}")),
]


def main():
    conn = open_readonly(DB)
    conn.create_function("REGEXP", 2, lambda pat, s: 1 if s is not None and re.search(pat, s, re.I) else 0)
    svc = Services(Store(DB), None, None)
    from main import get_live, get_twitch
    svc = Services(svc.store, get_live(), get_twitch)
    rows, passed = [], 0
    for cid, question, check in CASES:
        t = time.time()
        r = ask(svc, question, None, TODAY)
        ok, note = check(r, conn)
        passed += bool(ok)
        rows.append({"id": cid, "question": question, "ok": bool(ok), "note": note, "kind": r["kind"], "tool": r["tool"],
                     "seconds": round(time.time() - t, 1), "answer": r["answer"][:300]})
        print(f"{cid} {'PASS' if ok else 'FAIL'}  {question}\n      {note}")
    print(f"\nheld-out v2: {passed}/{len(CASES)}")
    out = HERE / "results" / (sys.argv[1] if len(sys.argv) > 1 else "heldout-v2.json")
    out.write_text(json.dumps({"passed": passed, "total": len(CASES), "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
