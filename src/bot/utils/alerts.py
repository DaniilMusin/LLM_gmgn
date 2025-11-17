import httpx
from ..config import settings
async def send_alert(text: str):
    tg = settings.telegram
    if not tg.enabled or not tg.bot_token or not tg.chat_id: return
    url = f"https://api.telegram.org/bot{tg.bot_token}/sendMessage"
    payload = {"chat_id": tg.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(url, json=payload)
    except Exception:
        pass
