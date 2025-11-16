from __future__ import annotations
import os, json, time, httpx
from typing import Optional, Dict, Any
from ..utils.keys import load_keys
from ..config import settings
STATE_PATH = os.path.join(settings.logging.out_dir, "pplx_keys.json")
os.makedirs(settings.logging.out_dir, exist_ok=True)
def _now() -> float: return time.time()
class PPLXKeyRing:
    def __init__(self): self._load_state(); self._reload_keys_file()
    def _load_state(self):
        try: self.state = json.load(open(STATE_PATH, "r", encoding="utf-8"))
        except Exception: self.state = {"current_idx": 0, "keys": []}
    def _save_state(self):
        try: json.dump(self.state, open(STATE_PATH, "w", encoding="utf-8"))
        except Exception: pass
    def _reload_keys_file(self):
        keys = load_keys("perplexity"); prev = {k.get("key"): k for k in self.state.get("keys", [])}
        arr = []
        for k in keys:
            entry = prev.get(k, {"key": k, "disabled": False, "cooldown_until": 0, "ok": 0, "err": 0, "last_error": None})
            entry["key"] = k; arr.append(entry)
        self.state["keys"] = arr
        if self.state.get("current_idx", 0) >= len(arr): self.state["current_idx"] = 0
        self._save_state()
    def reload(self): self._reload_keys_file()
    def status(self) -> Dict[str, Any]:
        return {"keys":[{"idx":i,"disabled":it.get("disabled", False),"cooldown_until":it.get("cooldown_until",0),
                         "cooldown_secs_left":max(0, int((it.get("cooldown_until",0) or 0) - _now())),
                         "ok":it.get("ok",0), "err":it.get("err",0), "last_error":it.get("last_error")} for i,it in enumerate(self.state.get("keys", []))],
                "current_idx": self.state.get("current_idx", 0), "count": len(self.state.get("keys", []))}
    def next_key(self) -> Optional[str]:
        keys = self.state.get("keys", []); 
        if not keys: return None
        n = len(keys); start = self.state.get("current_idx", 0)
        for step in range(n):
            idx = (start + step) % n; it = keys[idx]
            if it.get("disabled"): continue
            if _now() < float(it.get("cooldown_until",0) or 0): continue
            self.state["current_idx"] = idx; self._save_state(); return it["key"]
        return None
    def rotate(self) -> Optional[str]:
        keys = self.state.get("keys", []); 
        if not keys: return None
        self.state["current_idx"] = (self.state.get("current_idx", 0) + 1) % len(keys); self._save_state()
        return keys[self.state["current_idx"]]["key"]
    def mark_success(self, key: str):
        for it in self.state.get("keys", []):
            if it["key"] == key:
                it["ok"] = int(it.get("ok", 0)) + 1
                if _now() >= float(it.get("cooldown_until",0) or 0): it["cooldown_until"] = 0
                self._save_state(); return
    def mark_error(self, key: str, status: int, message: str | None):
        cd = 10
        if status == 429: cd = 60
        elif status == 401: cd = 24*3600
        elif status == 402 or (message and "insufficient" in str(message).lower()): cd = 30*24*3600
        elif status >= 500: cd = 30
        for it in self.state.get("keys", []):
            if it["key"] == key:
                it["err"] = int(it.get("err", 0)) + 1
                it["last_error"] = {"status": status, "message": message, "ts": _now()}
                it["cooldown_until"] = max(_now() + cd, float(it.get("cooldown_until",0) or 0))
                self._save_state(); return
ring = PPLXKeyRing()
PPLX_URL = "https://api.perplexity.ai/chat/completions"
async def pplx_chat(model: str, system: str, user: str, temperature: float = 0.2) -> dict:
    tried=set()
    while True:
        key = ring.next_key()
        if not key: raise RuntimeError("Perplexity: no available API keys")
        if key in tried and len(tried) >= max(1, len(ring.state.get("keys", []))): raise RuntimeError("Perplexity: all keys tried and failed")
        tried.add(key)
        body = {"model": model, "messages":[{"role":"system","content":system},{"role":"user","content":user}], "temperature": temperature}
        try:
            async with httpx.AsyncClient(timeout=60) as cli:
                r = await cli.post(PPLX_URL, json=body, headers={"Authorization": f"Bearer {key}", "Accept":"application/json"})
                if r.status_code == 200:
                    ring.mark_success(key); return r.json()
                else:
                    try:
                        j = r.json(); msg = (j.get("error") or {}).get("message") or j.get("message") or str(j)
                    except Exception:
                        msg = r.text
                    ring.mark_error(key, r.status_code, msg); continue
        except httpx.RequestError as e:
            ring.mark_error(key, 599, str(e)); continue
