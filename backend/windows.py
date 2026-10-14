import re
from datetime import date, datetime, timedelta, timezone

_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def month_window(month: str) -> tuple[datetime, datetime]:
    m = _MONTH_RE.match(month or "")
    if not m:
        raise ValueError("Month must look like YYYY-MM")
    year, mon = int(m.group(1)), int(m.group(2))
    if not 1 <= mon <= 12:
        raise ValueError("Month must be between 01 and 12")
    start = date(year, mon, 1)
    end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
    return _utc(start), _utc(end)


def range_window(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start:
        raise ValueError("End date is before start date")
    return _utc(start), _utc(end + timedelta(days=1))
