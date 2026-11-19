import ipaddress
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

PREFERRED = (
    "twitch.tv", "wikipedia.org", "7tv.app", "betterttv.com", "frankerfacez.com", "streamer.guide",
    "thestreamerawards.com", "streamscharts.com", "sullygnome.com", "twitchtracker.com", "streamelements.com",
    "streamlabs.com", "liquipedia.net",
)
USER_AGENT = "Mozilla/5.0 (compatible; local-research-bot)"
ALLOWED_PORTS = {80, 443, None}
MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3
PAGE_CHARS = 3000
SEARCH_RESULTS = 8
SEARCH_ATTEMPTS = 3
RETRY_PAUSE = 1.0
FETCH_PAGES = 3
PER_DOMAIN = 2


class WebUnavailable(Exception):
    pass


@dataclass
class Source:
    n: int
    title: str
    url: str
    domain: str
    text: str


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def is_public_url(url: str) -> bool:
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    if port not in ALLOWED_PORTS:
        return False
    try:
        infos = socket.getaddrinfo(parts.hostname, port or 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def _rank(results: list[dict]) -> list[dict]:
    def preferred(r: dict) -> int:
        d = domain_of(r.get("href", ""))
        return 0 if any(d == p or d.endswith("." + p) for p in PREFERRED) else 1

    ranked = sorted(results, key=preferred)
    seen: dict[str, int] = {}
    out = []
    for r in ranked:
        d = domain_of(r.get("href", ""))
        if not d or seen.get(d, 0) >= PER_DOMAIN:
            continue
        seen[d] = seen.get(d, 0) + 1
        out.append(r)
    return out


def search(query: str) -> list[dict]:
    from ddgs import DDGS

    q = query if "twitch" in query.lower() else f"{query} twitch"
    results: list[dict] = []
    for attempt in range(SEARCH_ATTEMPTS):
        try:
            results = DDGS().text(q, max_results=SEARCH_RESULTS)
            break
        except Exception as e:
            log.info("web search attempt %d failed: %s", attempt + 1, type(e).__name__)
            if attempt == SEARCH_ATTEMPTS - 1:
                raise WebUnavailable(f"search failed: {type(e).__name__}") from e
            time.sleep(RETRY_PAUSE * (attempt + 1))
    return _rank([r for r in results if r.get("href") and is_public_url(r["href"])])


def fetch_text(url: str, client: httpx.Client | None = None) -> str | None:
    import trafilatura

    own = client is None
    client = client or httpx.Client(timeout=8.0, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if not is_public_url(current):
                return None
            with client.stream("GET", current) as r:
                if r.is_redirect:
                    nxt = r.headers.get("location")
                    if not nxt:
                        return None
                    current = str(httpx.URL(current).join(nxt))
                    continue
                if r.status_code != 200 or not r.headers.get("content-type", "").startswith(("text/html", "text/plain")):
                    return None
                body = b""
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
            html = body.decode(r.encoding or "utf-8", errors="replace")
            text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
            return " ".join(text.split())[:PAGE_CHARS] or None
        return None
    except (httpx.HTTPError, OSError):
        return None
    finally:
        if own:
            client.close()


def gather(query: str) -> list[Source]:
    results = search(query)
    if not results:
        raise WebUnavailable("no results")
    top = results[:FETCH_PAGES]
    with ThreadPoolExecutor(FETCH_PAGES) as pool:
        pages = list(pool.map(lambda r: fetch_text(r["href"]), top))
    sources = []
    for i, (r, page) in enumerate(zip(top, pages), 1):
        text = page or " ".join((r.get("body") or "").split())
        if text:
            sources.append(Source(i, " ".join((r.get("title") or "").split())[:120], r["href"], domain_of(r["href"]), text))
    for r in results[FETCH_PAGES:FETCH_PAGES + 2]:
        snippet = " ".join((r.get("body") or "").split())
        if snippet:
            sources.append(Source(len(sources) + 1, " ".join((r.get("title") or "").split())[:120], r["href"], domain_of(r["href"]), snippet))
    if not sources:
        raise WebUnavailable("no readable results")
    return sources
