import asyncio, httpx, re
from datetime import datetime, timezone
from typing import AsyncIterator
from ..models import SocialPost
HUB_URL = "https://api.warpcast.com/v2/recent-casts"
async def poll_farcaster(interval=20) -> AsyncIterator[SocialPost]:
    seen=set()
    while True:
        try:
            async with httpx.AsyncClient(timeout=15) as cli:
                r = await cli.get(HUB_URL)
                if r.status_code != 200:
                    await asyncio.sleep(interval); continue
                data = r.json().get("result", {}).get("casts", [])
                for c in data:
                    key = c.get("hash") or c.get("url") or str(c.get("timestamp"))
                    if not key or key in seen: continue
                    seen.add(key)
                    text = c.get("text") or ""
                    syms = [m[1:] for m in re.findall(r"\$[A-Z0-9]{2,10}", text.upper())]
                    if not syms: continue
                    dt = datetime.fromtimestamp(int(c.get("timestamp", 0))/1000, tz=timezone.utc)
                    author = (c.get("author") or {}).get("username") or None
                    yield SocialPost(platform="farcaster", post_id=key, author_handle=author, created_at=dt, text=text, url=c.get("url"), symbols=syms, lang=None, engagement={})
        except Exception:
            pass
        await asyncio.sleep(interval)
