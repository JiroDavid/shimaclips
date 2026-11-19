import json
from datetime import date

import httpx

from ask.dates import resolve

OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.1:8b"

STREAMER = {"type": "string", "description": "the streamer's name exactly as the user wrote it, without @. Leave out if the user names no streamer."}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "count_clips",
            "description": "Count how many clips a streamer has in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "streamer": STREAMER,
                    "when": {"type": "string", "description": "date phrase such as 'this month', 'last week', '2026-03', 'March 2025', '2025'"},
                },
                "required": ["when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_clips",
            "description": "List a streamer's most viewed (or newest) clips in one date range. Use this for 'show me X's clips' or 'X's best clips' with no dates, passing when='all time'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "streamer": STREAMER,
                    "when": {"type": "string", "description": "date phrase such as 'this month', or 'all time' when no dates are given"},
                    "limit": {"type": "integer", "description": "how many clips, default 10"},
                    "sort": {"type": "string", "enum": ["views", "newest"]},
                },
                "required": ["when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_clips_by_month",
            "description": "Top clips for EACH month of a year, such as for a year rewind video.",
            "parameters": {
                "type": "object",
                "properties": {
                    "streamer": STREAMER,
                    "year": {"type": "integer", "description": "the year, for example 2026"},
                    "per_month": {"type": "integer", "description": "clips per month, default 10"},
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clips",
            "description": "Find clips about a specific topic or event by what is said in them. Only use this when the question names a topic; to just show a streamer's clips use top_clips. Use for any question about what happened, was said, or when something occurred, and for who or what a nickname, running joke or non-streamer is.",
            "parameters": {
                "type": "object",
                "properties": {
                    "streamer": STREAMER,
                    "query": {"type": "string", "description": "the topic to look for, as a short search phrase"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "streamer_info",
            "description": "Who a streamer is: their Twitch profile (bio, partner status, account age, live status) plus a few of their top clips. Use for 'who is <streamer>' or 'tell me about <streamer>'.",
            "parameters": {"type": "object", "properties": {"streamer": STREAMER}, "required": []},
        },
    },
]

SYSTEM = (
    "You route questions about a Twitch streamer's clips to exactly one tool. "
    "Always call exactly one tool, never reply in plain text. Never answer from memory. {default} "
    "Copy the date words from the question into 'when' exactly as the user wrote them, such as 'month before last' or 'last 7 days'. "
    "Never rephrase or simplify a date phrase and never compute dates."
)


def route(question: str, login: str | None) -> dict:
    resp = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": CHAT_MODEL,
            "stream": False,
            "options": {"temperature": 0},
            "tools": TOOLS,
            "messages": [
                {"role": "system", "content": SYSTEM.format(default=f"The default streamer is {login}, used when the question names none." if login else "There is no default streamer.")},
                {"role": "user", "content": question},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = {"prompt_tokens": body.get("prompt_eval_count", 0), "output_tokens": body.get("eval_count", 0)}
    calls = body["message"].get("tool_calls") or []
    if not calls:
        return {"tool": None, "args": {}, "usage": usage}
    fn = calls[0]["function"]
    args = fn["arguments"]
    if isinstance(args, str):
        args = json.loads(args)
    return {"tool": fn["name"], "args": args, "usage": usage}


def with_dates(args: dict, today: date) -> dict:
    out = {k: v for k, v in args.items() if k != "when"}
    if "when" in args:
        rng = resolve(str(args["when"]), today)
        if rng is None:
            raise ValueError(f"could not understand date phrase: {args['when']}")
        out["start"], out["end"] = rng[0].isoformat(), rng[1].isoformat()
    return out
