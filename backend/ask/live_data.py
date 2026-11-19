from datetime import date, timedelta

from ask.services import Services
from store import Streamer
from twitch import TwitchError


def ensure_range(svc: Services, streamer: Streamer, start: date, end_excl: date, need: int, today: date) -> bool:
    if svc.live is None:
        return True
    end = end_excl - timedelta(days=1)
    cached_total = svc.store.top_clips(streamer.broadcaster_id, start, end, 1, 0)[1]
    try:
        return svc.live.ensure_cached_first(streamer, start, end, need, today, cached_total)
    except TwitchError:
        if cached_total == 0:
            raise
        return False


def is_exact(svc: Services, streamer: Streamer, start: date, end_excl: date, today: date) -> bool:
    return svc.store.range_exact(
        streamer.broadcaster_id, start, end_excl - timedelta(days=1), streamer.account_created.date(), today
    )


def top_by_month(svc: Services, streamer: Streamer, year: int, per_month: int, today: date) -> list[dict]:
    last = today.month if year == today.year else 12
    months = []
    for m in range(1, last + 1):
        start = date(year, m, 1)
        end = date(year + (m == 12), m % 12 + 1, 1)
        ensure_range(svc, streamer, start, end, per_month, today)
        clips, total = svc.store.top_clips(streamer.broadcaster_id, start, end - timedelta(days=1), per_month, 0)
        months.append({
            "month": start.isoformat()[:7],
            "total_loaded": total,
            "exact": is_exact(svc, streamer, start, end, today),
            "clips": [
                {"id": c.id, "title": c.title, "url": c.url, "thumbnail_url": c.thumbnail_url,
                 "view_count": c.view_count, "duration": c.duration, "created_at": c.created_at}
                for c in clips
            ],
        })
    return months
