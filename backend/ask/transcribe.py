import subprocess
import sqlite3
import tempfile
import time
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


def transcribe_url(url: str) -> tuple[str, float, float]:
    with tempfile.TemporaryDirectory() as tmp:
        t0 = time.monotonic()
        path = download_clip(url, Path(tmp), "clip", lambda _p: None)
        t1 = time.monotonic()
        segments, _info = _load_model().transcribe(_decode_audio(path), vad_filter=True, beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
        t2 = time.monotonic()
    return text, t1 - t0, t2 - t1


def transcribe_missing(conn: sqlite3.Connection, clips: list[tuple[str, str]]) -> int:
    ensure_schema(conn)
    done = {r[0] for r in conn.execute("SELECT clip_id FROM transcripts")}
    n = 0
    for clip_id, url in clips:
        if clip_id in done:
            continue
        try:
            text, dl, tr = transcribe_url(url)
        except Exception as e:
            print(f"skip {clip_id}: {e}")
            continue
        conn.execute(
            "INSERT OR REPLACE INTO transcripts VALUES (?, ?, ?, ?, ?)",
            (clip_id, text, MODEL_NAME, dl, tr),
        )
        conn.commit()
        n += 1
    return n
