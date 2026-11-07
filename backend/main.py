import json
import os
from contextlib import asynccontextmanager
import threading
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from jobs import JobStore, job_to_dict, run_job
from loader import LoadManager, LoaderUnavailable, StreamerNotFound, normalize_login, state_to_dict
from store import Store
from twitch import TwitchClient, TwitchError

load_dotenv(Path(__file__).parent / ".env")



@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    with _deps_lock:
        manager = _manager
    if manager is not None:
        manager.shutdown()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

job_store = JobStore()
_twitch: TwitchClient | None = None


def get_twitch() -> TwitchClient:
    global _twitch
    if _twitch is None:
        client_id = os.environ.get("TWITCH_CLIENT_ID")
        secret = os.environ.get("TWITCH_CLIENT_SECRET")
        if not client_id or not secret:
            raise HTTPException(500, "Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in backend/.env")
        _twitch = TwitchClient(client_id, secret)
    return _twitch


_store: Store | None = None
_manager: LoadManager | None = None
_deps_lock = threading.Lock()


def get_store() -> Store:
    global _store
    with _deps_lock:
        if _store is None:
            default = Path(__file__).parent / "shimaclips.db"
            _store = Store(Path(os.environ.get("SHIMACLIPS_DB") or default))
        return _store


def get_manager() -> LoadManager:
    global _manager
    store = get_store()
    with _deps_lock:
        if _manager is None:
            _manager = LoadManager(store, get_twitch)
        return _manager


MAX_CALENDAR_DAYS = 400
ALLOWED_CLIP_HOSTS = {"clips.twitch.tv", "www.twitch.tv", "twitch.tv"}


class ClipRef(BaseModel):
    url: str
    title: str
    view_count: int

    @field_validator("url")
    @classmethod
    def twitch_only(cls, v: str) -> str:
        p = urlparse(v)
        host = (p.hostname or "").rstrip(".").lower()
        if p.scheme != "https" or host not in ALLOWED_CLIP_HOSTS or p.username or p.password:
            raise ValueError("Only Twitch clip URLs are allowed")
        return v


class DownloadRequest(BaseModel):
    clips: list[ClipRef] = Field(min_length=1)


@app.get("/api/streamers/search")
def search_streamers(q: str = Query(...), twitch: TwitchClient = Depends(get_twitch)):
    q = q.strip()
    if not 2 <= len(q) <= 40:
        raise HTTPException(422, "Search must be 2-40 characters")
    try:
        hits = twitch.search_channels(q)
    except TwitchError as e:
        raise HTTPException(502, str(e))
    return {"results": [
        {"login": h.login, "display_name": h.display_name, "avatar_url": h.thumbnail_url, "is_live": h.is_live}
        for h in hits[:8]
    ]}


@app.post("/api/streamers/{login}/load")
def load_streamer(login: str, mode: str = "auto", manager: LoadManager = Depends(get_manager)):
    if mode not in ("auto", "full"):
        raise HTTPException(422, "mode must be 'auto' or 'full'")
    try:
        normalize_login(login)
    except ValueError:
        raise HTTPException(422, "Streamer name must be 1-25 letters, numbers or underscores")
    try:
        streamer, state = manager.ensure(login, mode)
    except StreamerNotFound:
        raise HTTPException(404, f"Streamer '{normalize_login(login)}' not found")
    except LoaderUnavailable:
        raise HTTPException(503, "The server is shutting down")
    except TwitchError as e:
        raise HTTPException(502, str(e))
    return {
        "streamer": {
            "login": streamer.login,
            "display_name": streamer.display_name,
            "account_created": streamer.account_created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "state": state_to_dict(state),
    }


@app.get("/api/streamers/{login}/events")
def streamer_events(login: str, manager: LoadManager = Depends(get_manager)):
    if manager.state(login) is None:
        raise HTTPException(404, "Unknown streamer")

    def stream():
        while True:
            state = manager.state(login)
            yield f"data: {json.dumps(state_to_dict(state))}\n\n"
            if state.status in ("done", "error"):
                return
            time.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


def _known_streamer(login: str, store: Store):
    try:
        login = normalize_login(login)
    except ValueError:
        raise HTTPException(404, "Unknown streamer")
    streamer = store.get_streamer(login)
    if streamer is None:
        raise HTTPException(404, "Unknown streamer")
    return streamer


@app.get("/api/streamers/{login}/calendar")
def streamer_calendar(login: str, start: date, end: date, granularity: str = "month",
                      store: Store = Depends(get_store)):
    if granularity not in ("month", "day"):
        raise HTTPException(422, "granularity must be 'month' or 'day'")
    if end < start:
        raise HTTPException(422, "end must not be before start")
    if (end - start).days > MAX_CALENDAR_DAYS:
        raise HTTPException(422, f"Range must be at most {MAX_CALENDAR_DAYS} days")
    streamer = _known_streamer(login, store)
    buckets = store.bucket_counts(streamer.broadcaster_id, start, end, granularity)
    return {"buckets": [asdict(b) for b in buckets]}


@app.get("/api/streamers/{login}/clips")
def streamer_clips(login: str, start: date | None = None, end: date | None = None,
                   limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0),
                   store: Store = Depends(get_store)):
    if start is not None and end is not None and end < start:
        raise HTTPException(422, "end must not be before start")
    streamer = _known_streamer(login, store)
    clips, total = store.top_clips(streamer.broadcaster_id, start, end, limit, offset)
    return {"clips": [asdict(c) for c in clips], "total": total}


def start_job(job, clips) -> None:
    threading.Thread(target=run_job, args=(job, clips), daemon=True).start()


@app.post("/api/downloads")
def create_download(req: DownloadRequest):
    clips = [c.model_dump() for c in req.clips]
    job = job_store.create(clips)
    start_job(job, clips)
    return {"job_id": job.id}


@app.get("/api/downloads/{job_id}/events")
def download_events(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown download")

    def stream():
        while True:
            yield f"data: {json.dumps(job_to_dict(job))}\n\n"
            if job.status != "running":
                return
            time.sleep(0.5)

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.get("/api/downloads/{job_id}/file")
def download_file(job_id: str, background: BackgroundTasks):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown download")
    if job.status != "done" or job.file_path is None:
        raise HTTPException(409, "Download is not ready")
    background.add_task(job_store.remove, job_id)
    return FileResponse(job.file_path, filename=job.file_path.name)
