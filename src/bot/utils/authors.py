import os, json, math
from typing import Dict
from ..config import settings
PATH = os.path.join(settings.logging.out_dir, "authors.json")
os.makedirs(settings.logging.out_dir, exist_ok=True)
if not os.path.exists(PATH): json.dump({}, open(PATH,"w",encoding="utf-8"))
def _load() -> Dict[str, dict]:
    try: return json.load(open(PATH,"r",encoding="utf-8"))
    except Exception: return {}
def _save(data: Dict[str, dict]): json.dump(data, open(PATH,"w",encoding="utf-8"))
def update_from_post(author: str | None, engagement: dict | None = None, followers: int | None = None):
    if not author: return
    data = _load(); entry = data.get(author, {"score": 0.0, "posts": 0})
    base = 1.0
    if followers: base += math.log10(max(1, followers))
    if engagement: base += 0.1 * (engagement.get("likes",0)+engagement.get("replies",0)+engagement.get("num_comments",0))
    entry["score"] = min(100.0, entry["score"] + base); entry["posts"] = entry.get("posts", 0) + 1
    data[author] = entry; _save(data)
def weight(author: str | None) -> float:
    if not author: return 1.0
    sc = float(_load().get(author, {}).get("score", 0.0) or 0.0)
    return 1.0 + min(2.0, sc/50.0)
