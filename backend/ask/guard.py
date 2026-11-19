import json

import httpx

OLLAMA = "http://localhost:11434"
CHAT_MODEL = "llama3.1:8b"
LABELS = ("clips", "twitch_other", "off_topic")

SYSTEM = """You are a topic filter for an assistant that answers questions about Twitch streamers using their clips.
Choose exactly one label:
- clips: about a specific streamer, their clips, streams, stats, or what they said or did. Any subject counts if it is about the streamer or their clips (a streamer cooking, playing basketball, or talking about food is still clips).
- twitch_other: about Twitch or streaming in general but not answerable from clip data: awards, rankings, emotes, extensions, Twitch rules or policies, news, how to stream or grow a channel, and facts about a streamer as a person (their age, real name, birthplace, career). Questions about a streamer's relationships, dating, family or private life are clips: they are answered only from what the clips say.
- off_topic: nothing to do with Twitch, streamers or content creation: sports results, recipes, programming help, general knowledge, math.
Questions asking when, whether or what someone said, mentioned or talked about are clips, whatever the subject (sports, games, food and so on).
Reply with JSON only: {"label": "clips"} or {"label": "twitch_other"} or {"label": "off_topic"}.
Examples:
"top 10 clips for jasontheween this month" -> clips
"clips of him cooking" -> clips
"who is burger?" -> clips
"who is jasontheween" -> clips
"how old is ludwig" -> twitch_other
"where is stableronaldo from" -> twitch_other
"is arky dating anyone" -> clips
"what did he say about the nba" -> clips
"did jasontheween win a streamer award?" -> twitch_other
"is stableronaldo in the top 100 streamers" -> twitch_other
"what are 7tv emotes?" -> twitch_other
"how do I become a twitch affiliate" -> twitch_other
"who won the nba finals" -> off_topic
"give me a pasta recipe" -> off_topic
"write a python function to sort a list" -> off_topic"""


def classify(question: str, default_login: str | None = None) -> tuple[str, dict]:
    system = SYSTEM
    if default_login:
        system += f"\nThe user is currently looking at the clips of the streamer {default_login}, so questions about 'he' or 'him' refer to them."
    resp = httpx.post(
        f"{OLLAMA}/api/chat",
        json={
            "model": CHAT_MODEL,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": question}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    body = resp.json()
    usage = {"prompt_tokens": body.get("prompt_eval_count", 0), "output_tokens": body.get("eval_count", 0)}
    try:
        label = json.loads(body["message"]["content"]).get("label")
    except (ValueError, AttributeError):
        label = None
    return (label if label in LABELS else "clips"), usage
