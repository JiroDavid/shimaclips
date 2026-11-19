import subprocess
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from downloader import download_clip

MODEL_NAME = "small.en"

_model = None


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
    return _model


SCHEMA = """
CREATE TABLE IF NOT EXISTS transcripts (
    clip_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    download_s REAL NOT NULL,
    transcribe_s REAL NOT NULL
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _decode_audio(path: Path) -> np.ndarray:
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0


def _download(clip_id: str, url: str, tmp: Path) -> tuple[str, Path | None, float, str | None]:
    t0 = time.monotonic()
    try:
        path = download_clip(url, tmp, clip_id, lambda _p: None)
        return clip_id, path, time.monotonic() - t0, None
    except Exception as e:
        return clip_id, None, time.monotonic() - t0, str(e)


def transcribe_path(path: Path) -> tuple[str, float]:
    t0 = time.monotonic()
    segments, _info = _load_model().transcribe(_decode_audio(path), vad_filter=True, beam_size=1)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, time.monotonic() - t0


def transcribe_url(url: str) -> tuple[str, float, float]:
    with tempfile.TemporaryDirectory() as tmp:
        _id, path, dl, err = _download("clip", url, Path(tmp))
        if path is None:
            raise RuntimeError(err)
        text, tr = transcribe_path(path)
    return text, dl, tr


def transcribe_missing(conn: sqlite3.Connection, clips: list[tuple[str, str]], workers: int = 4) -> int:
    ensure_schema(conn)
    done = {r[0] for r in conn.execute("SELECT clip_id FROM transcripts")}
    todo = [(cid, url) for cid, url in clips if cid not in done]
    n = 0
    with tempfile.TemporaryDirectory() as tmp, ThreadPoolExecutor(workers) as pool:
        for clip_id, path, dl, err in pool.map(lambda c: _download(c[0], c[1], Path(tmp)), todo):
            if path is None:
                print(f"skip {clip_id}: {err}")
                continue
            try:
                text, tr = transcribe_path(path)
            except Exception as e:
                print(f"skip {clip_id}: {e}")
                continue
            finally:
                path.unlink(missing_ok=True)
            conn.execute(
                "INSERT OR REPLACE INTO transcripts VALUES (?, ?, ?, ?, ?)",
                (clip_id, text, MODEL_NAME, dl, tr),
            )
            conn.commit()
            n += 1
    return n
