import json
import re
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ask.answer import ask
from ask.history import History
from ask.services import Services

LOG_PATH = Path(__file__).parent.parent / "ask_log.jsonl"
LOGIN = re.compile(r"^[a-z0-9_]{1,25}$")
CONVERSATION_ID = re.compile(r"^[a-f0-9]{32}$")

_log_lock = threading.Lock()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)
    login: str | None = None
    conversation_id: str | None = None


class Rename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


def _log(entry: dict) -> None:
    with _log_lock, LOG_PATH.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _valid_id(conversation_id: str) -> str:
    if not CONVERSATION_ID.match(conversation_id):
        raise HTTPException(404, "Unknown conversation")
    return conversation_id


def make_router(get_store, get_live, get_twitch) -> APIRouter:
    router = APIRouter()

    def history(store) -> History:
        return History(store.path)

    @router.post("/api/ask")
    def post_ask(req: AskRequest, store=Depends(get_store), live=Depends(get_live)) -> dict:
        login = (req.login or "").strip().lower() or None
        if login is not None and not LOGIN.match(login):
            raise HTTPException(422, "invalid streamer login")
        hist = history(store)
        if req.conversation_id is not None and not (
            CONVERSATION_ID.match(req.conversation_id) and hist.exists(req.conversation_id)
        ):
            raise HTTPException(404, "Unknown conversation")
        question = req.question.strip()
        result = ask(Services(store, live, get_twitch), question, login)
        result["conversation_id"] = hist.add_turn(req.conversation_id, question, result)
        _log({
            "question": result["question"], "topic": result.get("topic"), "kind": result["kind"],
            "tool": result["tool"], "args": result["args"], "confident": result["confident"],
            "usage": result["usage"], "seconds": result["seconds"],
        })
        return result

    @router.get("/api/conversations")
    def list_conversations(store=Depends(get_store)) -> dict:
        return {"conversations": history(store).list()}

    @router.get("/api/conversations/{conversation_id}")
    def get_conversation(conversation_id: str, store=Depends(get_store)) -> dict:
        found = history(store).get(_valid_id(conversation_id))
        if found is None:
            raise HTTPException(404, "Unknown conversation")
        return found

    @router.put("/api/conversations/{conversation_id}")
    def rename_conversation(conversation_id: str, body: Rename, store=Depends(get_store)) -> dict:
        if not history(store).rename(_valid_id(conversation_id), body.title):
            raise HTTPException(404, "Unknown conversation")
        return {"ok": True}

    @router.delete("/api/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str, store=Depends(get_store)) -> dict:
        if not history(store).delete(_valid_id(conversation_id)):
            raise HTTPException(404, "Unknown conversation")
        return {"ok": True}

    return router
