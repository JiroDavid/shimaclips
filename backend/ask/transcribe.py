import ctypes
import glob
import importlib.util
import logging
import os
import subprocess
import sqlite3
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from downloader import download_clip
from workdir import work_dir

MODEL_NAME = "small.en"
TMP_PREFIX = "shimaclips_tr_"

log = logging.getLogger(__name__)
_model = None


def _preload_cuda_libs() -> None:
    pending: list[str] = []
    for pkg in ("nvidia.cublas", "nvidia.cudnn"):
        spec = importlib.util.find_spec(pkg)
        for base in (spec.submodule_search_locations or []) if spec else []:
            pending += glob.glob(os.path.join(base, "lib", "lib*.so*"))
    pending.sort(key=lambda p: ("Lt" not in p, p))
    for _ in range(3):
        pending = [lib for lib in pending if not _try_load(lib)]
        if not pending:
            return


def _try_load(lib: str) -> bool:
    try:
        ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
        return True
    except OSError:
        return False


def _load_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        try:
            _preload_cuda_libs()
            _model = WhisperModel(MODEL_NAME, device="cuda", compute_type="float16")
        except Exception:
            log.warning("GPU transcription unavailable, falling back to the CPU (much slower)", exc_info=True)
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
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
    with tempfile.TemporaryDirectory(prefix=TMP_PREFIX, dir=work_dir()) as tmp:
        _id, path, dl, err = _download("clip", url, Path(tmp))
        if path is None:
            raise RuntimeError(err)
        text, tr = transcribe_path(path)
    return text, dl, tr


def transcribe_missing(
    conn: sqlite3.Connection,
    clips: list[tuple[str, str]],
    workers: int = 4,
    on_clip: Callable[[], None] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> int:
    ensure_schema(conn)
    done = {r[0] for r in conn.execute("SELECT clip_id FROM transcripts")}
    todo = [(cid, url) for cid, url in clips if cid not in done]
    n = 0
    with tempfile.TemporaryDirectory(prefix=TMP_PREFIX, dir=work_dir()) as tmp, ThreadPoolExecutor(workers) as pool:
        for clip_id, path, dl, err in pool.map(lambda c: _download(c[0], c[1], Path(tmp)), todo):
            if should_stop():
                break
            if on_clip is not None:
                on_clip()
            if path is None:
                log.info("skip %s: %s", clip_id, err)
                continue
            try:
                text, tr = transcribe_path(path)
            except Exception as e:
                log.info("skip %s: %s", clip_id, e)
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
