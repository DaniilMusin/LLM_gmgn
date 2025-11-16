import os, json
from ..config import settings
PATH = os.path.join(settings.logging.out_dir, "control.json")
os.makedirs(settings.logging.out_dir, exist_ok=True)
_DEFAULT = {
    "dry_run": settings.execution.dry_run,
    "size_sol": settings.execution.default_trade_size_sol,
    "size_usdc": settings.execution.default_trade_size_usdc,
    "sources": {"bluesky": True,"reddit": True,"farcaster": False,"google_news": True,"rss": True}
}
def _load():
    try:
        data = json.load(open(PATH,"r",encoding="utf-8"))
        if not isinstance(data, dict): raise ValueError("control.json invalid")
        d = dict(_DEFAULT); d.update(data)
        s = dict(_DEFAULT["sources"]); s.update(data.get("sources", {}))
        d["sources"] = s
        return d
    except Exception:
        return dict(_DEFAULT)
def _save(data: dict):
    d = dict(_DEFAULT); d.update(data)
    s = dict(_DEFAULT["sources"]); s.update(d.get("sources", {}))
    d["sources"] = s
    json.dump(d, open(PATH,"w",encoding="utf-8"))
def get_state() -> dict: return _load()
def get_dry_run() -> bool: return bool(_load().get("dry_run", True))
def set_dry_run(v: bool): d=_load(); d["dry_run"]=bool(v); _save(d)
def get_size_sol() -> float: return float(_load().get("size_sol", _DEFAULT["size_sol"]))
def set_size_sol(v: float): d=_load(); d["size_sol"]=float(v); _save(d)
def get_size_usdc() -> float: return float(_load().get("size_usdc", _DEFAULT["size_usdc"]))
def set_size_usdc(v: float): d=_load(); d["size_usdc"]=float(v); _save(d)
def get_sources() -> dict: return dict(_load().get("sources", {}))
def is_source_enabled(name: str) -> bool: return bool(get_sources().get(name, False))
def set_source_enabled(name: str, enabled: bool): d=_load(); s=d.get("sources", {}); s[name]=bool(enabled); d["sources"]=s; _save(d)
