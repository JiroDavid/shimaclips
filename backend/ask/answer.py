import os
import re
import time
from dataclasses import asdict
from datetime import date, timedelta

import httpx

from ask.guard import classify
from ask.web_answer import WebUnavailable, answer_from_web
from ask.live_data import ensure_range, is_exact, top_by_month
from ask.router import CHAT_MODEL, OLLAMA, route, with_dates
from ask.search import search_clips
from ask.services import Services
from ask.streamers import all_mentioned, clean_login, mentioned, public, resolve, split_names, who_is_target
from ask.tools import ToolError, count_clips, open_readonly, top_clips
from twitch import TwitchError

OFF_TOPIC = "This isn't Twitch related, so I can't help with that. I can answer questions about streamers and their clips."
TWITCH_OTHER = (
    "That is about Twitch, but web lookups are turned off, so I can only answer from clip data and channel info. "
    "I can count clips, show a streamer's top clips (even month by month), or search what was said in transcribed clips."
)
WEB_DOWN = (
    "I couldn't reach the web just now to look that up (the search service didn't answer). "
    "Try again in a moment. I can still count clips, show top clips, or search what was said in transcribed clips."
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


BIO_MAX = 400
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
TYPES = {"partner": "a Twitch Partner", "affiliate": "a Twitch Affiliate"}


def _is_known(svc: Services, name: str | None, default_login: str) -> bool:
    login = clean_login(str(name or ""))
    return not login or login == default_login or login in svc.store.known_logins()


def _profile(svc: Services, streamer) -> dict | None:
    if svc.twitch is None:
        return None
    try:
        return svc.twitch().get_profile(streamer.broadcaster_id)
    except TwitchError:
        return None


def _streamer_info(svc: Services, conn, out: dict, streamer, today: date) -> None:
    profile = _profile(svc, streamer)
    kind = TYPES.get(profile["broadcaster_type"], "a Twitch streamer") if profile else "a Twitch streamer"
    parts = [f"{streamer.display_name} (twitch.tv/{streamer.login}) is {kind}. Their account was created on {streamer.account_created.date().isoformat()}."]
    if profile is not None:
        bio = EMAIL.sub("[email hidden]", profile["description"])[:BIO_MAX]
        parts.append(f'Their Twitch bio says: "{bio}"' if bio else "They have not written a Twitch bio.")
        if profile["is_live"]:
            game = f" playing {profile['game_name']}" if profile["game_name"] else ""
            parts.append(f"They are live right now{game}: {profile['stream_title']}")
    else:
        parts.append("I could not reach Twitch for their profile just now.")
    out["answer"] = " ".join(parts)
    _top_clips_context(svc, conn, out, streamer, today)


def _top_clips_context(svc: Services, conn, out: dict, streamer, today: date) -> None:
    ensure_range(svc, streamer, streamer.account_created.date(), today + timedelta(days=1), 5, today)
    clips, _total = svc.store.top_clips(streamer.broadcaster_id, None, None, 5, 0)
    row = conn.execute(
        "SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM clips WHERE broadcaster_id = ?", (streamer.broadcaster_id,)
    ).fetchone()
    out["sources"] = [asdict(c) for c in clips]
    if clips:
        out["after"] = (
            f"Here are some of {streamer.display_name}'s most viewed clips stored in our system. "
            f"I hold {row[0]:,} of their clips, from {row[1][:10]} to {row[2][:10]}."
        )


def _web_flow(svc: Services, question: str, default_login: str | None, out: dict, usage: dict, today: date) -> None:
    if os.environ.get("SHIMACLIPS_WEB") == "0":
        out["kind"], out["answer"], out["confident"] = "refusal", TWITCH_OTHER, False
        return
    try:
        web = answer_from_web(svc.db_path, question)
    except (WebUnavailable, httpx.HTTPError):
        out["answer"], out["confident"] = WEB_DOWN, False
        return
    _add(usage, web["usage"])
    out["answer"], out["confident"] = web["answer"], web["confident"]
    out["web_sources"] = web["sources"]
    out["web"] = {"cached": web["cached"], "seconds": web["seconds"]}
    name = mentioned(svc, question) or default_login
    res = resolve(svc, name) if name else None
    if res is not None and res["status"] == "ok":
        streamer = res["streamer"]
        out["streamer"] = public(streamer)
        conn = open_readonly(svc.db_path)
        try:
            _top_clips_context(svc, conn, out, streamer, today)
        finally:
            conn.close()


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
            sort = args.get("sort", "views")
            ensure_range(svc, streamer, start, end, limit, today)
            exact = is_exact(svc, streamer, start, end, today)
            notes = []
            if sort == "newest" and not exact:
                sort = "views"
                notes.append("Newest first needs a fully loaded period, so these are sorted by views instead.")
            r = top_clips(conn, streamer.login, args["start"], args["end"], limit, sort)
            out["data"] = r
            out["sources"] = r["clips"]
            if not r["clips"]:
                out["answer"] = f"I couldn't find any clips for {streamer.display_name} between {r['start']} and {r['end']}."
            else:
                label = "newest" if sort == "newest" else "top"
                out["answer"] = f"Here are the {label} {len(r['clips'])} clips for {streamer.display_name}, {r['start']} to {r['end']}."
                if not exact:
                    notes.append("This period isn't fully loaded yet, so there may be clips with more views than these.")
            out["after"] = " ".join(notes)
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
        _streamer_info(svc, conn, out, streamer, today)
    else:
        out["answer"] = "I could not work out how to answer that with the clip library."
        out["confident"] = False


def ask(svc: Services, question: str, default_login: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    t0 = time.monotonic()
    usage = dict(NO_USAGE)
    out: dict = {
        "question": question, "kind": "answer", "tool": None, "args": {}, "streamer": None,
        "suggestions": [], "sources": [], "months": [], "confident": True, "after": "", "web_sources": [],
    }

    def finish() -> dict:
        out["usage"] = usage
        out["seconds"] = round(time.monotonic() - t0, 2)
        return out

    label, u = classify(question, default_login)
    _add(usage, u)
    out["topic"] = label
    if label == "off_topic":
        out["kind"], out["answer"], out["confident"] = "refusal", OFF_TOPIC, False
        return finish()
    if label == "twitch_other":
        try:
            _web_flow(svc, question, default_login, out, usage, today)
        except TwitchError as e:
            out["kind"], out["answer"], out["confident"] = "error", f"Twitch did not respond: {e}", False
        return finish()

    target = who_is_target(svc, question, default_login)
    if target is not None:
        routed = {"tool": "streamer_info", "args": {"streamer": target}, "usage": dict(NO_USAGE)}
        out["shortcut"] = "who-is question about a known streamer"
    else:
        routed = route(question, default_login)
    _add(usage, routed["usage"])
    if routed["tool"] is None:
        routed = {"tool": "search_clips", "args": {"query": question}, "usage": routed["usage"]}
        out["fallback"] = "no tool chosen, searched clips instead"
    args = dict(routed["args"])
    name = args.pop("streamer", None) or mentioned(svc, question) or default_login
    if routed["tool"] == "streamer_info" and default_login and not _is_known(svc, name, default_login):
        routed = {"tool": "search_clips", "args": {"query": question}, "usage": routed["usage"]}
        args, name = dict(routed["args"]), default_login
        out["fallback"] = "not a known streamer, searched the clips instead"
    out["tool"], out["args"] = routed["tool"], routed["args"]
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
