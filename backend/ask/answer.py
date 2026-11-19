import sqlite3
import time
from datetime import date

import httpx

from ask.router import CHAT_MODEL, OLLAMA, route, with_dates
from ask.search import search_clips
from ask.tools import ToolError, count_clips, top_clips

LOW_CONFIDENCE_ANSWER = (
    "I could not find clips that clearly match this. These are the closest ones, "
    "but I would not rely on them. Clips only cover moments that someone chose to clip."
)

ANSWER_SYSTEM = (
    "You answer a question about a Twitch streamer using ONLY the numbered clips given. "
    "Cite clips as [1], [2]. Each clip has a clip date, which is when it was clipped and may differ "
    "from when the stream happened. If the clips do not answer the question, say so plainly. "
    "Do not invent details. Keep it under 80 words."
)


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


def ask(conn: sqlite3.Connection, question: str, login: str, today: date | None = None) -> dict:
    today = today or date.today()
    t0 = time.monotonic()
    routed = route(question, login)
    usage = dict(routed["usage"])
    out: dict = {"question": question, "tool": routed["tool"], "args": routed["args"], "sources": [], "confident": True}
    try:
        args = with_dates(routed["args"], today)
        args.setdefault("login", login)
        if routed["tool"] == "count_clips":
            r = count_clips(conn, **args)
            out["answer"] = f"{r['login']} has {r['count']} clips from {r['start']} up to (not including) {r['end']}."
            out["data"] = r
        elif routed["tool"] == "top_clips":
            r = top_clips(conn, **args)
            out["answer"] = f"Top {len(r['clips'])} clips for {r['login']}, {r['start']} to {r['end']}."
            out["sources"] = r["clips"]
            out["data"] = r
        elif routed["tool"] == "search_clips":
            r = search_clips(conn, **args)
            out["sources"] = r["results"]
            out["confident"] = r["confident"]
            if not r["results"]:
                out["answer"] = "No transcribed clips matched."
            elif not r["confident"]:
                out["answer"] = LOW_CONFIDENCE_ANSWER
            else:
                out["answer"], u = _generate(question, r["results"])
                usage = {k: usage[k] + u[k] for k in usage}
        else:
            out["answer"] = "I could not work out how to answer that with the clip library."
            out["confident"] = False
    except (ToolError, ValueError, TypeError) as e:
        out["answer"] = f"I could not run that: {e}"
        out["confident"] = False
    out["usage"] = usage
    out["seconds"] = round(time.monotonic() - t0, 2)
    return out
