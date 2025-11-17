import asyncio, feedparser, time, re
from datetime import datetime, timezone
from typing import AsyncIterator, List
from ..models import SocialPost
def _parse_feed(url: str):
    feed = feedparser.parse(url)
    for e in feed.entries:
        yield {"title": getattr(e, "title", ""), "link": getattr(e, "link", ""), "published": getattr(e, "published_parsed", None)}
async def poll_reddit_subs(subs: List[str], interval=60) -> AsyncIterator[SocialPost]:
    seen=set()
    while True:
        for sub in subs:
            url=f"https://www.reddit.com/r/{sub}/new/.rss"
            try:
                for row in _parse_feed(url):
                    key=row["link"]
                    if not key or key in seen: continue
                    seen.add(key)
                    ts=time.mktime(row["published"]) if row["published"] else time.time()
                    dt=datetime.fromtimestamp(ts, tz=timezone.utc)
                    title=row["title"] or ""
                    syms=[m[1:] for m in re.findall(r"\$[A-Z0-9]{2,10}", title.upper())]
                    if not syms: continue
                    yield SocialPost(platform="reddit", post_id=key, created_at=dt, text=title, url=row["link"], symbols=syms, lang=None, engagement={})
            except Exception as e:
                # BUG FIX #51: Log reddit errors for debugging
                from ..utils.logging import logger
                logger.error(f"Reddit polling error for r/{sub}: {e}")
                continue
        await asyncio.sleep(interval)
