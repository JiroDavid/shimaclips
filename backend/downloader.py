import re
from pathlib import Path
from typing import Callable

import yt_dlp

_UNSAFE = re.compile(r"[^\w\- .()\[\]]", re.UNICODE)
_NO_WORD_CHARS = re.compile(r"^[\W_]*$", re.UNICODE)


def safe_title(title: str) -> str:
    cleaned = _UNSAFE.sub("", title or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned or _NO_WORD_CHARS.match(cleaned):
        return "clip"
    return cleaned[:60].rstrip(" .")


def clip_basename(index: int, views: int, title: str) -> str:
    return f"{index:02d}_{views}views_{safe_title(title)}"


def _glob_escape(s: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", s)


def download_clip(url: str, dest_dir: Path, basename: str, on_progress: Callable[[float], None]) -> Path:
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(99.0, d["downloaded_bytes"] / total * 100))

    opts = {
        "outtmpl": str(Path(dest_dir) / f"{basename}.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "allowed_extractors": ["twitch:clips"],
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    matches = sorted(Path(dest_dir).glob(f"{_glob_escape(basename)}.*"))
    if not matches:
        raise RuntimeError("Download finished but no file was produced")
    return matches[0]
