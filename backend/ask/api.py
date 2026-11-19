import json
import re
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ask.answer import ask
from ask.tools import open_readonly

DB_PATH = Path(__file__).parent.parent / "shimaclips.db"
LOG_PATH = Path(__file__).parent.parent / "ask_log.jsonl"
LOGIN = re.compile(r"^[a-z0-9_]{1,25}$")

router = APIRouter()
_log_lock = threading.Lock()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    login: str


def _log(entry: dict) -> None:
    with _log_lock, LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


@router.post("/api/ask")
def post_ask(req: AskRequest) -> dict:
    login = req.login.strip().lower()
    if not LOGIN.match(login):
        raise HTTPException(422, "invalid streamer login")
    conn = open_readonly(DB_PATH)
    try:
        result = ask(conn, req.question.strip(), login)
    finally:
        conn.close()
    _log({k: result[k] for k in ("question", "tool", "args", "confident", "usage", "seconds")})
    return result
