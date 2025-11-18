import asyncio, time, re
from datetime import datetime, timezone
from typing import AsyncIterator
from urllib.parse import quote_plus
from ..models import NewsItem

# BUG FIX #54: Make feedparser optional to allow bot to run without RSS
try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False
    feedparser = None
COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss/"
COINTELE_RSS = "https://cointelegraph.com/rss"
DECRYPT_RSS  = "https://decrypt.co/feed"
def _parse_feed(url: str):
    if not FEEDPARSER_AVAILABLE:
        return []
    feed = feedparser.parse(url)
    for e in feed.entries:
        yield {"title": getattr(e, "title", ""), "link": getattr(e, "link", ""), "published": getattr(e, "published_parsed", None)}
async def poll_rss(interval=60) -> AsyncIterator[NewsItem]:
    if not FEEDPARSER_AVAILABLE:
        from ..utils.logging import logger
        logger.warning("feedparser not available, RSS feeds disabled")
        while True:
            await asyncio.sleep(interval)
            continue
    seen = set(); feeds = [COINDESK_RSS, COINTELE_RSS, DECRYPT_RSS]
    while True:
        for url in feeds:
            try:
                for row in _parse_feed(url):
                    key = row["link"]
                    if not key or key in seen: continue
                    seen.add(key)
                    ts = time.mktime(row["published"]) if row["published"] else time.time()
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    title = row["title"] or ""
                    syms = [m[1:] for m in re.findall(r"\$[A-Z0-9]{2,10}", title.upper())]
                    yield NewsItem(source=url.split("/")[2], title=title, url=row["link"], published_at=dt, symbols=syms)
            except Exception as e:
                # BUG FIX #52: Log RSS feed errors for debugging
                from ..utils.logging import logger
                logger.error(f"RSS feed polling error for {url}: {e}")
                continue
        await asyncio.sleep(interval)
def google_news_rss(query: str, hl="en-US", gl="US", ceid="US:en") -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={hl}&gl={gl}&ceid={ceid}"
async def poll_google_news(queries: list[str], hl="en-US", gl="US", ceid="US:en", interval=300):
    if not FEEDPARSER_AVAILABLE:
        from ..utils.logging import logger
        logger.warning("feedparser not available, Google News disabled")
        while True:
            await asyncio.sleep(interval)
            continue
    seen = set()
    while True:
        for q in queries:
            url = google_news_rss(q, hl=hl, gl=gl, ceid=ceid)
            try:
                for row in _parse_feed(url):
                    key = row["link"]
                    if not key or key in seen: continue
                    seen.add(key)
                    ts = time.mktime(row["published"]) if row["published"] else time.time()
                    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                    yield NewsItem(source="news.google.com", title=row["title"], url=row["link"], published_at=dt, symbols=[])
            except Exception as e:
                # BUG FIX #52: Log Google News errors for debugging
                from ..utils.logging import logger
                logger.error(f"Google News polling error for query '{q}': {e}")
                continue
        await asyncio.sleep(interval)
