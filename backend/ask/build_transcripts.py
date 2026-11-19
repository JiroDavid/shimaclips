import sqlite3
import sys
import time

from ask.subset import pick_subset
from ask.transcribe import transcribe_missing

DB = "shimaclips.db"


def main(limit: int) -> None:
    conn = sqlite3.connect(DB, timeout=120)
    subset = pick_subset(conn, "jasontheween", "2026-01-01")
    print(f"subset size {len(subset)}", flush=True)
    start = time.monotonic()
    for i in range(0, min(limit, len(subset)), 50):
        n = transcribe_missing(conn, subset[i:i + 50])
        print(f"{i + 50} processed, {n} new, {time.monotonic() - start:.0f}s", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
