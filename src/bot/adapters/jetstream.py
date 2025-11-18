import asyncio, json, websockets
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, Any
from ..models import SocialPost
from ..utils.text import extract_symbols
from ..utils import authors
WSS = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post"
async def stream_bluesky() -> AsyncIterator[SocialPost]:
    backoff = 1
    while True:
        try:
            async with websockets.connect(WSS, ping_interval=20) as ws:
                async for raw in ws:
                    evt: Dict[str, Any] = json.loads(raw)
                    if evt.get("kind") != "commit": continue
                    c = evt.get("commit", {})
                    if c.get("operation") != "create" or c.get("collection") != "app.bsky.feed.post": continue
                    rec = c.get("record", {}) or {}
                    text = rec.get("text", "") or ""
                    syms = extract_symbols(text)
                    if not syms: continue
                    created = rec.get("createdAt")
                    dt = datetime.fromisoformat(created.replace("Z","+00:00")) if created else datetime.now(timezone.utc)
                    authors.update_from_post(evt.get("did"), None, None)
                    yield SocialPost(platform="bluesky", post_id=c.get("rkey",""), author_handle=evt.get("did"),
                                     created_at=dt, text=text,
                                     url=f"https://bsky.app/profile/{evt.get('did')}/post/{c.get('rkey')}",
                                     symbols=syms, lang=None, engagement={})
                backoff = 1
        except Exception as e:
            # BUG FIX #46: Log websocket errors to track connection issues
            from ..utils.logging import logger
            logger.error(f"Bluesky jetstream error: {e}. Reconnecting in {min(30, backoff)}s...")
            await asyncio.sleep(min(30, backoff)); backoff *= 2
