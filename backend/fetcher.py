from datetime import datetime, timedelta, timezone

from store import Store
from twitch import User

GRACE = timedelta(days=2)


def _next_month(d: datetime) -> datetime:
    return datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=timezone.utc)


def month_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    cur = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    out = []
    while cur <= end:
        nxt = _next_month(cur)
        out.append((cur, nxt))
        cur = nxt
    return out


def split_window(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    midnight = start.hour == start.minute == start.second == 0
    if midnight and start.day == 1 and end == _next_month(start):
        step = timedelta(days=1)
    elif midnight and end - start == timedelta(days=1):
        step = timedelta(hours=1)
    else:
        return []
    out = []
    cur = start
    while cur < end:
        out.append((cur, cur + step))
        cur += step
    return out


def plan_windows(store: Store, user: User, mode: str, now: datetime) -> None:
    if mode not in ("auto", "full"):
        raise ValueError(f"unknown fetch mode: {mode}")
    store.add_windows(user.id, month_windows(user.created_at, now))
    store.reset_windows(user.id, "nonfinal" if mode == "auto" else "all", now, GRACE)


def run_fetch(store: Store, twitch, broadcaster_id: str,
              now=lambda: datetime.now(timezone.utc)) -> None:
    while (w := store.next_pending(broadcaster_id)) is not None:
        result = twitch.fetch_window(broadcaster_id, w.start, w.end)
        store.upsert_clips(broadcaster_id, result.clips)
        if result.truncated:
            children = split_window(w.start, w.end)
            if children:
                store.mark_split(broadcaster_id, w.start, w.end, children)
                continue
        store.mark_done(broadcaster_id, w.start, w.end, now(), result.truncated)
