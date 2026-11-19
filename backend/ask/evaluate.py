import json
import sys
import time
from datetime import date
from pathlib import Path

from ask.answer import ask
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


def run_structured(conn, cases, default_login, today):
    results = []
    for c in cases:
        login = c.get("login", default_login)
        r = ask(conn, c["question"], default_login, today)
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


def main() -> None:
    golden = json.loads((HERE / "eval" / "golden.json").read_text())
    today = date.fromisoformat(golden["today"])
    conn = open_readonly(DB)
    out: dict = {"ran_at": time.strftime("%Y-%m-%d %H:%M:%S"), "today": golden["today"]}
    structured = run_structured(conn, golden["structured"], golden["login"], today)
    out["structured"] = structured
    passed = sum(r["passed"] for r in structured)
    print(f"structured: {passed}/{len(structured)} exact")
    for r in structured:
        if not r["passed"]:
            print("  FAIL", r["id"], r["question"], {k: r[k] for k in ("tool_ok", "args_ok", "value_ok", "got_tool", "got_args")})
    (HERE / "eval" / "results").mkdir(exist_ok=True)
    path = HERE / "eval" / "results" / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(out, indent=2))
    print("saved", path.name)


if __name__ == "__main__":
    main()
