import json
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ask.answer import ask
from ask.services import Services

LOG_PATH = Path(__file__).parent.parent / "ask_log.jsonl"
LOGIN = re.compile(r"^[a-z0-9_]{1,25}$")

_log_lock = threading.Lock()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    login: str | None = None


def _log(entry: dict) -> None:
    with _log_lock, LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def make_router(get_store, get_live, get_twitch) -> APIRouter:
    router = APIRouter()

    @router.post("/api/ask")
    def post_ask(req: AskRequest, store=Depends(get_store), live=Depends(get_live)) -> dict:
        login = (req.login or "").strip().lower() or None
        if login is not None and not LOGIN.match(login):
            raise HTTPException(422, "invalid streamer login")
        result = ask(Services(store, live, get_twitch), req.question.strip(), login)
        _log({
            "question": result["question"], "topic": result.get("topic"), "kind": result["kind"],
            "tool": result["tool"], "args": result["args"], "confident": result["confident"],
            "usage": result["usage"], "seconds": result["seconds"],
        })
        return result

    return router
