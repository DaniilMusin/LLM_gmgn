from __future__ import annotations
import json, httpx, re
from ..models import Decision
from ..config import settings
from .perplexity_client import pplx_chat
SYSTEM = "You are a crypto event & trading decision engine. Return STRICT JSON by schema."
def _schema(): return Decision.model_json_schema()
def _parse_decision(text: str) -> Decision:
    try: return Decision.model_validate_json(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}$", text.strip())
        if m: return Decision.model_validate(json.loads(m.group(0)))
        text2 = text.strip().strip('`'); return Decision.model_validate(json.loads(text2))
async def _ask_pplx(model: str, payload: dict) -> Decision:
    res = await pplx_chat(model, SYSTEM, json.dumps(payload, ensure_ascii=False), temperature=0.2)
    text = res.get("choices", [{}])[0].get("message", {}).get("content") or res.get("output_text") or res.get("answer") or ""
    if not text: raise RuntimeError("Perplexity returned empty content")
    return _parse_decision(text)
async def decide(payload: dict) -> Decision:
    return await _ask_pplx(settings.perplexity.model_fast, payload | {"_stage": "filter"})
