import argparse
import threading
import time

import main
from ask import transcription
from ask.services import Services


def monitor(label: str, job: transcription.Job, stop: threading.Event) -> None:
    start = time.time()
    while not stop.wait(30):
        pct = round(100 * job.processed / job.total) if job.total else 0
        print(f"[{label}] {job.state} {job.processed}/{job.total} ({pct}%) {int((time.time() - start) / 60)} min", flush=True)


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Transcribe streamers' clips ahead of time")
    parser.add_argument("logins", nargs="+")
    parser.add_argument("--cap", type=int, default=2000)
    args = parser.parse_args()
    transcription.CAP, transcription.TOP_DAYS, transcription.PER_DAY, transcription.FLOOR_PER_DAY = args.cap, 90, 20, 3
    store = main.get_store()
    manager = transcription.TranscriptionManager(Services(store, main.get_live(), main.get_twitch))
    for login in args.logins:
        streamer = store.get_streamer(login)
        if streamer is None:
            user = main.get_twitch().get_user(login)
            if user is None:
                print(f"[{login}] not found on Twitch, skipping", flush=True)
                continue
            store.upsert_streamer(user)
            streamer = store.get_streamer(user.login)
        job = transcription.Job()
        stop = threading.Event()
        threading.Thread(target=monitor, args=(streamer.login, job, stop), daemon=True).start()
        started = time.time()
        try:
            manager._run(streamer, job)
        finally:
            stop.set()
        print(f"[{streamer.login}] {job.state}: {job.processed}/{job.total} clips in {int((time.time() - started) / 60)} min"
              + (f" ({job.error})" if job.error else ""), flush=True)


if __name__ == "__main__":
    main_cli()
