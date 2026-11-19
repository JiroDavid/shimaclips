import json
from datetime import date

import httpx

from ask.dates import resolve

OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.1:8b"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "count_clips",
            "description": "Count how many clips a streamer has in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "login": {"type": "string", "description": "streamer login, lowercase"},
                    "when": {"type": "string", "description": "date phrase such as 'this month', 'last week', '2026-03', 'March 2025', '2025'"},
                },
                "required": ["login", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_clips",
            "description": "List a streamer's most viewed (or newest) clips in a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "login": {"type": "string"},
                    "when": {"type": "string", "description": "date phrase such as 'this month'"},
                    "limit": {"type": "integer", "description": "how many clips, default 10"},
                    "sort": {"type": "string", "enum": ["views", "newest"]},
                },
                "required": ["login", "when"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_clips",
            "description": "Find clips about a topic or event by what is said in them. Use for any question about what happened, was said, or when something occurred.",
            "parameters": {
                "type": "object",
                "properties": {
                    "login": {"type": "string"},
                    "query": {"type": "string", "description": "the topic to look for, as a short search phrase"},
                },
                "required": ["login", "query"],
            },
        },
    },
]

SYSTEM = (
    "You route questions about a Twitch streamer's clip library to exactly one tool. "
    "Never answer from memory. The streamer defaults to {login} unless another is named. "
    "Pass date phrases through unchanged in 'when'; do not compute dates."
)


def route(question: str, login: str) -> dict:
    resp = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": CHAT_MODEL,
            "stream": False,
            "options": {"temperature": 0},
            "tools": TOOLS,
            "messages": [
                {"role": "system", "content": SYSTEM.format(login=login)},
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
