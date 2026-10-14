import json
import os
import threading
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from jobs import JobStore, job_to_dict, run_job
from twitch import TwitchClient, TwitchError, top_clips
from windows import month_window, range_window

load_dotenv(Path(__file__).parent / ".env")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

store = JobStore()
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


class SearchRequest(BaseModel):
    streamer: str
    count: int = Field(10, ge=1, le=200)
    month: str | None = None
    start: date | None = None
    end: date | None = None

    @field_validator("streamer")
    @classmethod
    def streamer_not_blank(cls, v: str) -> str:
        if not v.strip().lstrip("@"):
            raise ValueError("Streamer name is required")
        return v

    @model_validator(mode="after")
    def has_window(self):
        if not self.month and not (self.start and self.end):
            raise ValueError("Provide a month, or both a start and end date")
        return self


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


@app.post("/api/clips/search")
def search_clips(req: SearchRequest, twitch: TwitchClient = Depends(get_twitch)):
    try:
        start, end = month_window(req.month) if req.month else range_window(req.start, req.end)
    except ValueError as e:
        raise HTTPException(422, str(e))
    try:
        user_id = twitch.get_user_id(req.streamer)
        if user_id is None:
            raise HTTPException(404, f"Streamer '{req.streamer.strip().lstrip('@')}' not found")
        clips = twitch.get_clips(user_id, start, end)
    except TwitchError as e:
        raise HTTPException(502, str(e))
    return {"clips": [asdict(c) for c in top_clips(clips, req.count)], "total_in_window": len(clips)}


def start_job(job, clips) -> None:
    threading.Thread(target=run_job, args=(job, clips), daemon=True).start()


@app.post("/api/downloads")
def create_download(req: DownloadRequest):
    clips = [c.model_dump() for c in req.clips]
    job = store.create(clips)
    start_job(job, clips)
    return {"job_id": job.id}


@app.get("/api/downloads/{job_id}/events")
def download_events(job_id: str):
    job = store.get(job_id)
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
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown download")
    if job.status != "done" or job.file_path is None:
        raise HTTPException(409, "Download is not ready")
    background.add_task(store.remove, job_id)
    return FileResponse(job.file_path, filename=job.file_path.name)
