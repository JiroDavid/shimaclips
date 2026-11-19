import os
import shutil
import time
from pathlib import Path


def work_dir() -> Path:
    base = Path(os.environ.get("SHIMACLIPS_WORKDIR") or Path(__file__).parent / ".work")
    base.mkdir(parents=True, exist_ok=True)
    return base


def sweep(prefix: str, base: Path | None = None, older_than: float = 0.0) -> int:
    base = base or work_dir()
    cutoff = time.time() - older_than
    removed = 0
    for path in base.glob(f"{prefix}*"):
        try:
            if path.is_dir() and path.stat().st_mtime <= cutoff:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed
