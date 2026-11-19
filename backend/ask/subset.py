import sqlite3


def pick_subset(
    conn: sqlite3.Connection,
    login: str,
    since: str,
    top_days: int = 90,
    per_day: int = 20,
    floor_per_day: int = 3,
) -> list[tuple[str, str]]:
    rows = conn.execute(
        "SELECT k.id, k.url, substr(k.created_at, 1, 10) AS day, k.view_count "
        "FROM clips k JOIN streamers s USING (broadcaster_id) "
        "WHERE s.login = ? AND k.created_at >= ? "
        "ORDER BY k.view_count DESC",
        (login, since),
    ).fetchall()
    by_day: dict[str, list[tuple[str, str, int]]] = {}
    for clip_id, url, day, views in rows:
        by_day.setdefault(day, []).append((clip_id, url, views))
    ranked = sorted(by_day, key=lambda d: (len(by_day[d]), sum(v for _, _, v in by_day[d])), reverse=True)
    big = set(ranked[:top_days])
    picked: list[tuple[str, str]] = []
    for day, clips in by_day.items():
        limit = per_day if day in big else floor_per_day
        picked.extend((cid, url) for cid, url, _ in clips[:limit])
    return picked
