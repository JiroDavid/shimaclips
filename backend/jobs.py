import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from downloader import clip_basename, download_clip

JOB_TTL_SECONDS = 3600


@dataclass
class Item:
    name: str
    status: str = "pending"
    percent: float = 0.0
    error: str | None = None


@dataclass
class Job:
    id: str
    dir: Path
    items: list[Item]
    status: str = "running"
    file_path: Path | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)


class JobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, clips: list[dict]) -> Job:
        self._prune()
        job = Job(
            id=uuid.uuid4().hex,
            dir=Path(tempfile.mkdtemp(prefix="shimaclips_")),
            items=[Item(name=clip_basename(i + 1, c["view_count"], c["title"])) for i, c in enumerate(clips)],
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def remove(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job:
            shutil.rmtree(job.dir, ignore_errors=True)

    def _prune(self) -> None:
        cutoff = time.time() - JOB_TTL_SECONDS
        for job_id in [j.id for j in list(self._jobs.values()) if j.created < cutoff]:
            self.remove(job_id)


def run_job(job: Job, clips: list[dict], fetch=download_clip) -> None:
    try:
        done: list[Path] = []
        for item, clip in zip(job.items, clips):
            item.status = "downloading"

            def on_progress(p: float, item=item) -> None:
                item.percent = p

            try:
                path = fetch(clip["url"], job.dir, item.name, on_progress)
                item.status = "done"
                item.percent = 100.0
                done.append(path)
            except Exception as e:
                item.status = "failed"
                item.error = str(e)
        if not done:
            job.status = "error"
            job.error = "All clip downloads failed"
            return
        if len(done) == 1:
            job.file_path = done[0]
        else:
            zip_path = job.dir / "clips.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                for p in done:
                    z.write(p, p.name)
            job.file_path = zip_path
        job.status = "done"
    except Exception as e:
        job.status = "error"
        job.error = str(e)


def job_to_dict(job: Job) -> dict:
    return {
        "status": job.status,
        "error": job.error,
        "items": [
            {"name": i.name, "status": i.status, "percent": i.percent, "error": i.error}
            for i in job.items
        ],
    }
