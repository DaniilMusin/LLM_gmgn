import os, json, math, threading
from typing import Dict
from ..config import settings
PATH = os.path.join(settings.logging.out_dir, "authors.json")
os.makedirs(settings.logging.out_dir, exist_ok=True)
# BUG FIX #58: Initialize file properly with context manager
if not os.path.exists(PATH):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump({}, f)
# BUG FIX #59: Thread-safe lock for authors.json operations
_AUTHORS_LOCK = threading.Lock()
def _load() -> Dict[str, dict]:
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}
def _save(data: Dict[str, dict]):
    # BUG FIX #58: Use atomic write to prevent file corruption
    try:
        temp_path = PATH + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(temp_path, PATH)  # Atomic on POSIX systems
    except Exception:
        pass
def update_from_post(author: str | None, engagement: dict | None = None, followers: int | None = None):
    if not author: return
    # BUG FIX #59: Thread-safe operations with lock
    with _AUTHORS_LOCK:
        data = _load(); entry = data.get(author, {"score": 0.0, "posts": 0})
        base = 1.0
        if followers: base += math.log10(max(1, followers))
        if engagement: base += 0.1 * (engagement.get("likes",0)+engagement.get("replies",0)+engagement.get("num_comments",0))
        entry["score"] = min(100.0, entry["score"] + base); entry["posts"] = entry.get("posts", 0) + 1
        data[author] = entry; _save(data)
def weight(author: str | None) -> float:
    if not author: return 1.0
    # BUG FIX #59: Thread-safe read with lock
    with _AUTHORS_LOCK:
        sc = float(_load().get(author, {}).get("score", 0.0) or 0.0)
        return 1.0 + min(2.0, sc/50.0)
