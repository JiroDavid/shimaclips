import time
from datetime import date

import httpx

from ask.guard import classify
from ask.live_data import ensure_range, is_exact, top_by_month
from ask.router import CHAT_MODEL, OLLAMA, route, with_dates
from ask.search import search_clips
from ask.services import Services
from ask.streamers import all_mentioned, mentioned, public, resolve, split_names
from ask.tools import ToolError, count_clips, open_readonly, top_clips
from twitch import TwitchError

OFF_TOPIC = "This isn't Twitch related, so I can't help with that. I can answer questions about streamers and their clips."
TWITCH_OTHER = (
    "That is about Twitch, but I can only answer from clip data and channel info, and I can't look things up on the web. "
    "I can count clips, show a streamer's top clips (even month by month), or search what was said in transcribed clips."
)

ANSWER_SYSTEM = (
    "You answer a question about a Twitch streamer using ONLY the numbered clips given. "
    "Cite clips as [1], [2]. Each clip has a clip date, which is when it was clipped and may differ "
    "from when the stream happened. If the clips do not answer the question, say so plainly. "
    "Do not invent details. Keep it under 80 words. Do not claim anything about people beyond what the clips say."
)

NO_USAGE = {"prompt_tokens": 0, "output_tokens": 0}


def _add(total: dict, extra: dict) -> None:
    for k in total:
        total[k] += extra.get(k, 0)


def _generate(question: str, results: list[dict]) -> tuple[str, dict]:
    context = "\n".join(
        f"[{i}] clip date {r['created_at'][:10]}, title: {r['title']}. Transcript: {r['transcript']}"
        for i, r in enumerate(results, 1)
    )
    resp = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": CHAT_MODEL,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": f"Clips:\n{context}\n\nQuestion: {question}"},
            ],
        },
        timeout=180,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = {"prompt_tokens": body.get("prompt_eval_count", 0), "output_tokens": body.get("eval_count", 0)}
    return body["message"]["content"].strip(), usage


def _transcribed(conn, broadcaster_id: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM transcripts t JOIN clips k ON k.id = t.clip_id WHERE k.broadcaster_id = ?",
        (broadcaster_id,),
    ).fetchone()[0]


def _unknown_streamer_answer(res: dict) -> str:
    if res["suggestions"]:
        names = ", ".join(s["display_name"] for s in res["suggestions"])
        return f"Hey, I couldn't find a streamer called '{res['name']}'. Did you mean one of these: {names}?"
    return f"Hey, I couldn't find a streamer called '{res['name']}'. Check the spelling and try again."


def _run_tool(svc: Services, conn, out: dict, usage: dict, question: str, tool: str, args: dict, streamer, today: date) -> None:
    bid = streamer.broadcaster_id
    if tool in ("count_clips", "top_clips"):
        args = with_dates(args, today)
        start, end = date.fromisoformat(args["start"]), date.fromisoformat(args["end"])
        if tool == "count_clips":
            r = count_clips(conn, streamer.login, args["start"], args["end"])
            r["exact"] = is_exact(svc, streamer, start, end, today)
            out["data"] = r
            if r["exact"]:
                out["answer"] = f"{streamer.display_name} has {r['count']:,} clips from {r['start']} up to (not including) {r['end']}."
            elif r["count"] == 0:
                out["answer"] = (
                    f"I don't have {streamer.display_name}'s clips for that period loaded yet, so I can't count them. "
                    "Open their calendar to load them."
                )
                out["confident"] = False
            else:
                out["answer"] = (
                    f"At least {r['count']:,} clips from {r['start']} up to (not including) {r['end']}. "
                    "This period isn't fully loaded, so the real number is higher."
                )
        else:
            limit = max(1, min(int(args.get("limit", 10)), 50))
            ensure_range(svc, streamer, start, end, limit, today)
            r = top_clips(conn, streamer.login, args["start"], args["end"], limit, args.get("sort", "views"))
            out["data"] = r
            out["sources"] = r["clips"]
            out["answer"] = f"Here are the top {len(r['clips'])} clips for {streamer.display_name}, {r['start']} to {r['end']}."
            if not is_exact(svc, streamer, start, end, today):
                out["after"] = "This period isn't fully loaded yet, so there may be clips with more views than these."
    elif tool == "top_clips_by_month":
        year = int(args.get("year", today.year))
        if not 2007 <= year <= today.year:
            raise ValueError(f"year must be between 2007 and {today.year}")
        per_month = max(1, min(int(args.get("per_month", 10)), 20))
        months = top_by_month(svc, streamer, year, per_month, today)
        out["months"] = months
        total = sum(len(m["clips"]) for m in months)
        out["answer"] = f"Here are the top {per_month} clips for each month of {year} for {streamer.display_name}."
        out["after"] = f"That is {total} clips across {len(months)} months."
        if not all(m["exact"] for m in months):
            out["after"] += " Months marked as not fully loaded may be missing some clips."
    elif tool == "search_clips":
        if _transcribed(conn, bid) == 0:
            out["answer"] = (
                f"I haven't transcribed {streamer.display_name}'s clips, so I can't search by topic for them. "
                "I can still count their clips or show their top clips."
            )
            out["confident"] = False
            return
        r = search_clips(conn, streamer.login, args["query"])
        out["sources"] = r["results"]
        out["confident"] = r["confident"]
        if not r["results"]:
            out["answer"] = "No transcribed clips matched."
        elif not r["confident"]:
            missing = ", ".join(f"'{w}'" for w in r["unseen_words"])
            out["answer"] = (
                f"I could not find anything about this: no transcribed clip mentions {missing}. "
                "These are the closest clips by meaning, but they probably do not match. "
                "Only top clips from 2026 are transcribed."
            )
        else:
            text, u = _generate(question, r["results"])
            _add(usage, u)
            days = sorted(x["created_at"][:10] for x in r["results"])
            span = days[0] if days[0] == days[-1] else f"{days[0]} and {days[-1]}"
            out["answer"] = text
            out["after"] = (
                f"The cited clips were made on or between {span}. "
                "A clip date is when the clip was made, not necessarily when the stream happened."
            )
    elif tool == "streamer_info":
        row = conn.execute(
            "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM clips WHERE broadcaster_id = ?", (bid,)
        ).fetchone()
        out["answer"] = (
            f"{streamer.display_name} (twitch.tv/{streamer.login}) created their account on "
            f"{streamer.account_created.date().isoformat()}. I hold {row[0]:,} of their clips"
            + (f", from {row[1][:10]} to {row[2][:10]}." if row[0] else ".")
        )
    else:
        out["answer"] = "I could not work out how to answer that with the clip library."
        out["confident"] = False


def ask(svc: Services, question: str, default_login: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    t0 = time.monotonic()
    usage = dict(NO_USAGE)
    out: dict = {
        "question": question, "kind": "answer", "tool": None, "args": {}, "streamer": None,
        "suggestions": [], "sources": [], "months": [], "confident": True, "after": "",
    }

    def finish() -> dict:
        out["usage"] = usage
        out["seconds"] = round(time.monotonic() - t0, 2)
        return out

    label, u = classify(question, default_login)
    _add(usage, u)
    out["topic"] = label
    if label != "clips":
        out["kind"] = "refusal"
        out["answer"] = OFF_TOPIC if label == "off_topic" else TWITCH_OTHER
        out["confident"] = False
        return finish()

    routed = route(question, default_login)
    _add(usage, routed["usage"])
    if routed["tool"] is None:
        routed = {"tool": "search_clips", "args": {"query": question}, "usage": routed["usage"]}
        out["fallback"] = "no tool chosen, searched clips instead"
    out["tool"], out["args"] = routed["tool"], routed["args"]
    args = dict(routed["args"])
    name = args.pop("streamer", None) or mentioned(svc, question) or default_login
    if not name:
        out["kind"] = "needs_streamer"
        out["answer"] = "Which streamer do you mean? Include their name, for example 'jasontheween'."
        out["confident"] = False
        return finish()

    try:
        res = None
        for candidate in split_names(str(name)):
            res = resolve(svc, candidate)
            if res["status"] == "ok":
                break
        if res["status"] == "unknown" and mentioned(svc, question):
            res = resolve(svc, mentioned(svc, question))
        if res["status"] == "ok" and max(len(all_mentioned(svc, question)), len(split_names(str(name)))) > 1:
            out["note"] = f"I can only search one streamer at a time, so I used {res['streamer'].display_name}."
        if res["status"] == "error":
            out["kind"], out["answer"], out["confident"] = "error", f"I couldn't reach Twitch to look that streamer up: {res['message']}", False
            return finish()
        if res["status"] == "unknown":
            out["kind"], out["suggestions"] = "unknown_streamer", res["suggestions"]
            out["answer"], out["confident"] = _unknown_streamer_answer(res), False
            return finish()
        streamer = res["streamer"]
        out["streamer"] = public(streamer)
        conn = open_readonly(svc.db_path)
        try:
            _run_tool(svc, conn, out, usage, question, routed["tool"], args, streamer, today)
        finally:
            conn.close()
    except (ToolError, ValueError, TypeError) as e:
        out["answer"], out["confident"] = f"I could not run that: {e}", False
    except TwitchError as e:
        out["kind"], out["answer"], out["confident"] = "error", f"Twitch did not respond: {e}", False
    return finish()
