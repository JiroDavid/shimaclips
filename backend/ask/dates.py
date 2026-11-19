import re
from datetime import date, timedelta

MONTHS = {
    name: i + 1
    for i, name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"]
    )
}


def _month_number(word: str) -> int | None:
    if len(word) < 3:
        return None
    for name, number in MONTHS.items():
        if name == word or (word in ("sept",) and name == "september") or (len(word) == 3 and name.startswith(word)):
            return number
    return None


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1)
    return start, end


def resolve(phrase: str, today: date) -> tuple[date, date] | None:
    """Turn a date phrase into a half-open range [start, end), or None if not understood."""
    p = re.sub(r"^(?:in|during|for|from|of|over|within)\s+", "", phrase.strip(" ?.!,").lower())
    if p in ("all time", "ever", "all", "of all time"):
        return date(2007, 1, 1), today + timedelta(days=1)
    if p == "today":
        return today, today + timedelta(days=1)
    if p == "yesterday":
        return today - timedelta(days=1), today
    if p == "this week":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=7)
    if p == "last week":
        monday = today - timedelta(days=today.weekday())
        return monday - timedelta(days=7), monday
    if p == "this month":
        return _month_range(today.year, today.month)
    if p == "last month":
        first = date(today.year, today.month, 1)
        prev = first - timedelta(days=1)
        return _month_range(prev.year, prev.month)
    if p in ("the month before last", "month before last"):
        last_month_end = date(today.year, today.month, 1) - timedelta(days=1)
        earlier = date(last_month_end.year, last_month_end.month, 1) - timedelta(days=1)
        return _month_range(earlier.year, earlier.month)
    m = re.fullmatch(r"(?:the )?(?:past|last|previous) (\d{1,4}) days?", p)
    if m and int(m[1]) >= 1:
        n = int(m[1])
        return today - timedelta(days=n - 1), today + timedelta(days=1)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
        try:
            d = date.fromisoformat(p)
        except ValueError:
            return None
        return d, d + timedelta(days=1)
    if p == "this year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1)
    if p == "last year":
        return date(today.year - 1, 1, 1), date(today.year, 1, 1)
    if re.fullmatch(r"\d{4}", p):
        y = int(p)
        return date(y, 1, 1), date(y + 1, 1, 1)
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m and 1 <= int(m[2]) <= 12:
        return _month_range(int(m[1]), int(m[2]))
    m = re.fullmatch(r"([a-z]+)(?: (\d{4}))?", p)
    if m and _month_number(m[1]):
        return _month_range(int(m[2]) if m[2] else today.year, _month_number(m[1]))
    return None
