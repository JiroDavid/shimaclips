import json
import re
import shutil
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

from ask.answer import ask
from ask.embed import embed_query
from ask.keyword import fuse, keyword_search
from ask.retrieve import load_matrix, top_k
from ask.guard import classify
from ask.router import route
from ask.services import Services
from ask.streamers import clean_login, mentioned
from store import Store
from ask.tools import open_readonly

HERE = Path(__file__).parent
DB = HERE.parent / "shimaclips.db"


def _bid(conn, login):
    return conn.execute("SELECT broadcaster_id FROM streamers WHERE login = ?", (login,)).fetchone()[0]


def expected_count(conn, login, start, end) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ?",
        (_bid(conn, login), start, end),
    ).fetchone()[0]


def expected_top_views(conn, login, start, end, limit, sort) -> list[int]:
    order = "view_count DESC" if sort == "views" else "created_at DESC"
    rows = conn.execute(
        f"SELECT view_count FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ? "
        f"ORDER BY {order} LIMIT ?",
        (_bid(conn, login), start, end, limit),
    ).fetchall()
    return [r[0] for r in rows]


def run_structured(conn, svc, cases, default_login, today):
    results = []
    for c in cases:
        login = c.get("login", default_login)
        r = ask(svc, c["question"], default_login, today)
        data = r.get("data") or {}
        tool_ok = r["tool"] == c["tool"]
        args_ok = data.get("start") == c["start"] and data.get("end") == c["end"] and data.get("login") == login
        if c["tool"] == "count_clips":
            value_ok = data.get("count") == expected_count(conn, login, c["start"], c["end"])
        else:
            got = [s["view_count"] for s in r["sources"]] if c["sort"] == "views" else None
            want = expected_top_views(conn, login, c["start"], c["end"], c["limit"], c["sort"])
            if got is None:
                got_ids = [s["created_at"] for s in r["sources"]]
                want_rows = conn.execute(
                    "SELECT created_at FROM clips WHERE broadcaster_id = ? AND created_at >= ? AND created_at < ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (_bid(conn, login), c["start"], c["end"], c["limit"]),
                ).fetchall()
                value_ok = got_ids == [w[0] for w in want_rows]
            else:
                value_ok = got == want and len(got) == len(want)
        results.append({
            "id": c["id"], "question": c["question"], "tool_ok": tool_ok, "args_ok": args_ok,
            "value_ok": value_ok, "passed": tool_ok and args_ok and value_ok,
            "got_tool": r["tool"], "got_args": r["args"], "usage": r["usage"], "seconds": r["seconds"],
        })
    return results


def run_retrieval(conn, entries, broadcaster_id):
    t_ids, t_mat = load_matrix(conn, "transcript", broadcaster_id)
    k_ids, k_mat = load_matrix(conn, "title", broadcaster_id)
    modes = ["title_embed", "transcript_embed", "keyword", "hybrid"]
    per_mode = {m: [] for m in modes}
    detail = []
    for e in entries:
        rel = set(e["relevant"])
        qv = embed_query(e["question"])
        lists = {
            "title_embed": top_k(qv, k_ids, k_mat, k=5),
            "transcript_embed": top_k(qv, t_ids, t_mat, k=5),
            "keyword": keyword_search(conn, e["question"], k=5, broadcaster_id=broadcaster_id),
        }
        lists["hybrid"] = fuse([top_k(qv, t_ids, t_mat, k=20), keyword_search(conn, e["question"], k=20, broadcaster_id=broadcaster_id)], k=5)
        row = {"id": e["id"], "n_relevant": len(rel)}
        for m in modes:
            ids = [h.clip_id for h in lists[m]]
            hits = [i in rel for i in ids]
            rr = next((1 / (i + 1) for i, h in enumerate(hits) if h), 0.0)
            per_mode[m].append({"hit": any(hits), "precision": sum(hits) / 5, "rr": rr})
            row[m] = {"hit": any(hits), "p5": sum(hits) / 5}
        detail.append(row)
    summary = {}
    for m in modes:
        r = per_mode[m]
        summary[m] = {
            "hit@5": round(sum(x["hit"] for x in r) / len(r), 3),
            "precision@5": round(sum(x["precision"] for x in r) / len(r), 3),
            "mrr": round(sum(x["rr"] for x in r) / len(r), 3),
        }
    return summary, detail


def run_pipeline(conn, svc, entries, login, today, kind):
    out = []
    for e in entries:
        r = ask(svc, e["question"], login, today)
        rel = set(e.get("relevant", []))
        cited = [s["id"] for s in r["sources"]]
        row = {"id": e["id"], "question": e["question"], "tool": r["tool"], "tool_ok": r["tool"] == "search_clips",
               "confident": r["confident"], "cited_relevant": sum(c in rel for c in cited), "cited": len(cited),
               "answer": r["answer"], "usage": r["usage"], "seconds": r["seconds"]}
        if kind == "mixed":
            lo, hi = e["expected_window"]
            row["cited_in_window"] = sum(lo <= s["created_at"][:10] <= hi for s in r["sources"])
        if kind == "abstain":
            row["abstained"] = not r["confident"]
        out.append(row)
    return out


def run_web(cases):
    from ask.web_answer import answer_from_web
    from workdir import work_dir

    folder = Path(tempfile.mkdtemp(prefix="shimaclips_eval_", dir=work_dir()))
    rows = []
    try:
        for c in cases:
            try:
                r = answer_from_web(folder / "web.db", c["question"])
            except Exception as e:
                rows.append({"id": c["id"], "question": c["question"], "kind": c["kind"], "unavailable": type(e).__name__, "ok": None})
                continue
            valid = {s["n"] for s in r["sources"]}
            cited = {int(n) for n in re.findall(r"\[(\d+)\]", r["answer"])}
            if c["kind"] == "answerable":
                hit = any(k.lower() in r["answer"].lower() for k in c["any_of"])
                ok = r["confident"] and bool(cited) and cited <= valid and hit
            else:
                ok = not r["confident"]
            rows.append({"id": c["id"], "question": c["question"], "kind": c["kind"], "ok": ok, "confident": r["confident"],
                         "cited": sorted(cited), "sources": len(r["sources"]), "seconds": r["seconds"],
                         "tokens": sum(r["usage"].values()), "answer": r["answer"]})
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return rows


def run_injection(cases):
    from ask.web import Source
    from ask.web_answer import _generate

    good = {
        "What are 7TV emotes?": "7TV is a third-party browser extension that adds custom emotes to Twitch chat for viewers who install it.",
        "What is a Twitch raid?": "A raid lets a streamer send their live viewers to another channel when their stream ends.",
        "What are Twitch channel points?": "Channel points are a loyalty program where viewers earn points for watching and spend them on custom rewards.",
    }
    rows = []
    for c in cases:
        sources = [
            Source(1, "Evil page", "https://evil.example/", "evil.example", c["evil"]),
            Source(2, "Real page", "https://example.org/real", "example.org", good[c["question"]]),
        ]
        text, _ = _generate(c["question"], sources)
        leaked = [f for f in c["forbidden"] if f in text.lower()]
        rows.append({"id": c["id"], "question": c["question"], "ok": not leaked, "leaked": leaked, "answer": text})
    return rows


def run_guard(cases, default_login):
    from ask.guard import SYSTEM
    rows = []
    for c in cases:
        label, _ = classify(c["question"], default_login)
        rows.append({"question": c["question"], "want": c["label"], "got": label, "ok": label == c["label"],
                     "in_prompt": c["question"].lower() in SYSTEM.lower()})
    return rows


def run_routing(cases, svc):
    rows = []
    for c in cases:
        r = route(c["question"], c["default"])
        got = r["args"].get("streamer")
        got = clean_login(str(got)) if got else None
        rows.append({"question": c["question"], "want_tool": c["tool"], "got_tool": r["tool"], "want_streamer": c["streamer"],
                     "got_streamer": got, "with_safety_net": (got or mentioned(svc, c["question"])) == c["streamer"] or (c["streamer"] is None and (got or mentioned(svc, c["question"]) or c["default"]) == c["default"]) and r["tool"] == c["tool"], "ok": r["tool"] == c["tool"] and (got == c["streamer"] or (c["streamer"] is None and got == c["default"]))})
    return rows


def main() -> None:
    golden = json.loads((HERE / "eval" / "golden.json").read_text())
    today = date.fromisoformat(golden["today"])
    conn = open_readonly(DB)
    svc = Services(Store(DB), None, None)
    out: dict = {"ran_at": time.strftime("%Y-%m-%d %H:%M:%S"), "today": golden["today"]}
    structured = run_structured(conn, svc, golden["structured"], golden["login"], today)
    out["structured"] = structured
    passed = sum(r["passed"] for r in structured)
    print(f"structured: {passed}/{len(structured)} exact")
    for r in structured:
        if not r["passed"]:
            print("  FAIL", r["id"], r["question"], {k: r[k] for k in ("tool_ok", "args_ok", "value_ok", "got_tool", "got_args")})
    scored = golden["semantic"] + golden["mixed"]
    summary, detail = run_retrieval(conn, scored, _bid(conn, golden["login"]))
    out["retrieval"], out["retrieval_detail"] = summary, detail
    print("retrieval over", len(scored), "questions")
    for m, v in summary.items():
        print(f"  {m:17} hit@5 {v['hit@5']:.2f}  precision@5 {v['precision@5']:.2f}  mrr {v['mrr']:.2f}")
    for kind in ("semantic", "mixed", "abstain"):
        res = run_pipeline(conn, svc, golden[kind], golden["login"], today, kind)
        out["pipeline_" + kind] = res
        print(kind, "tool ok", sum(r["tool_ok"] for r in res), "/", len(res),
              "| confident", sum(r["confident"] for r in res), "| avg s", round(sum(r["seconds"] for r in res) / len(res), 1))
    web = run_web(golden["web"])
    out["web"] = web
    scored = [r for r in web if r["ok"] is not None]
    print(f"web answers: {sum(r['ok'] for r in scored)}/{len(scored)} correct ({len(web) - len(scored)} skipped, search unavailable)")
    for r in scored:
        if not r["ok"]:
            print("  WRONG", r["id"], r["kind"], r["question"], "->", r["answer"][:160].replace("\n", " "))
    injection = run_injection(golden["injection"])
    out["injection"] = injection
    print(f"prompt injection resisted: {sum(r['ok'] for r in injection)}/{len(injection)}")
    for r in injection:
        if not r["ok"]:
            print("  FOLLOWED", r["id"], r["leaked"], "->", r["answer"][:160].replace("\n", " "))
    guard = run_guard(golden["guard"], golden["login"])
    out["guard"] = guard
    unseen = [r for r in guard if not r["in_prompt"]]
    print(f"topic guard: {sum(r['ok'] for r in guard)}/{len(guard)} correct, {sum(r['ok'] for r in unseen)}/{len(unseen)} on questions not in the prompt examples")
    for r in guard:
        if not r["ok"]:
            print("  WRONG", r["question"], "want", r["want"], "got", r["got"])
    routing = run_routing(golden["routing"], svc)
    out["routing"] = routing
    print(f"routing and streamer extraction: {sum(r['ok'] for r in routing)}/{len(routing)} from the model alone, {sum(r['with_safety_net'] for r in routing)}/{len(routing)} with the known-streamer safety net")
    for r in routing:
        if not r["ok"]:
            print("  WRONG", r["question"], "want", r["want_tool"], r["want_streamer"], "got", r["got_tool"], r["got_streamer"])
    (HERE / "eval" / "results").mkdir(exist_ok=True)
    path = HERE / "eval" / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=2))
    print("saved", path.name)


if __name__ == "__main__":
    main()
