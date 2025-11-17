from collections import defaultdict, deque
from math import sqrt
from datetime import datetime, timedelta, timezone
from ..models import SocialPost
from ..utils import authors
import re, os, pickle, threading
from ..config import settings
RED_FLAGS = re.compile(r"\b(airdrop|giveaway|presale|100x|insider|signal)\b", re.I)
class RollingStats:
    def __init__(self, maxlen=180): self.buf = deque(maxlen=maxlen)
    def push(self, x: float): self.buf.append(x)
    def z(self, x: float) -> float:
        if not self.buf: return 0.0
        m = sum(self.buf)/len(self.buf)
        v = sum((y-m)**2 for y in self.buf)/len(self.buf)
        s = sqrt(v) if v>0 else 1.0
        return (x - m)/s
class HypeAggregator:
    def __init__(self, window_secs=900, auto_load=True):
        self._lock = threading.Lock()  # Thread-safe lock for concurrent updates
        self.window = timedelta(seconds=window_secs)
        self.posts = defaultdict(list)
        self.stats_mentions = defaultdict(RollingStats)
        self.stats_authors  = defaultdict(RollingStats)
        self.stats_author_weight = defaultdict(RollingStats)
        self.stats_eng      = defaultdict(RollingStats)
        self._state_path = os.path.join(settings.logging.out_dir, "hype_state.pkl")
        if auto_load:
            self.load_state()
    def update(self, post: SocialPost):
        with self._lock:
            # BUG FIX #6: Use datetime.now(timezone.utc) instead of deprecated utcnow()
            now = datetime.now(timezone.utc)
            for sym in post.symbols:
                self.posts[sym].append((now, post))
                self.posts[sym] = [(t,p) for (t,p) in self.posts[sym] if now - t <= self.window]
    def hype_score(self, symbol: str):
        with self._lock:
            window_posts = self.posts.get(symbol, [])
            mentions = len(window_posts)
            author_set = {p.author_handle for _,p in window_posts if p.author_handle}
            unique_authors = len(author_set)
            wsum = sum(authors.weight(p.author_handle) for _,p in window_posts)
            eng = 0.0
            for _,p in window_posts:
                m = p.engagement or {}; denom = max(1, (p.author_followers or 0))
                eng += (m.get("likes",0)+m.get("score",0)+m.get("replies",0)+m.get("num_comments",0)) / denom
            red_flag = any(RED_FLAGS.search(p.text or "") for _,p in window_posts)
            z_m = self.stats_mentions[symbol].z(mentions); self.stats_mentions[symbol].push(mentions)
            z_a = self.stats_authors[symbol].z(unique_authors); self.stats_authors[symbol].push(unique_authors)
            z_aw = self.stats_author_weight[symbol].z(wsum); self.stats_author_weight[symbol].push(wsum)
            z_e = self.stats_eng[symbol].z(eng); self.stats_eng[symbol].push(eng)
            score = z_m + 0.35*z_a + 0.15*z_aw + 0.30*z_e - (0.6 if red_flag else 0.0)
            return score, {"mentions":mentions,"unique_authors":unique_authors,"author_weight_sum":wsum,"eng_approx":eng,"red_flag":red_flag,"z_m":z_m,"z_a":z_a,"z_aw":z_aw,"z_e":z_e}

    def save_state(self):
        """Сохраняет текущее состояние HypeAggregator в файл."""
        with self._lock:
            try:
                os.makedirs(settings.logging.out_dir, exist_ok=True)
                # Подготавливаем данные для сериализации
                state = {
                    "window_secs": int(self.window.total_seconds()),
                    "posts": dict(self.posts),  # конвертируем defaultdict в dict
                    "stats_mentions": {k: list(v.buf) for k, v in self.stats_mentions.items()},
                    "stats_authors": {k: list(v.buf) for k, v in self.stats_authors.items()},
                    "stats_author_weight": {k: list(v.buf) for k, v in self.stats_author_weight.items()},
                    "stats_eng": {k: list(v.buf) for k, v in self.stats_eng.items()},
                    # BUG FIX #6: Use datetime.now(timezone.utc) instead of deprecated utcnow()
                    "saved_at": datetime.now(timezone.utc).isoformat()
                }
                # BUG FIX #49: Use atomic write to prevent file corruption
                temp_path = self._state_path + ".tmp"
                with open(temp_path, "wb") as f:
                    pickle.dump(state, f)
                # Atomic rename on POSIX systems
                os.replace(temp_path, self._state_path)
            except Exception as e:
                # BUG FIX #49: Log save errors for debugging
                from ..utils.logging import logger
                logger.error(f"Failed to save hype state: {e}")
                pass

    def load_state(self):
        """Загружает состояние HypeAggregator из файла."""
        with self._lock:
            try:
                if not os.path.exists(self._state_path):
                    return
                # BUG NOTE #13: pickle.load() can execute arbitrary code if file is malicious
                # Acceptable risk in this context as file is bot-generated and in trusted directory
                with open(self._state_path, "rb") as f:
                    state = pickle.load(f)

                # Восстанавливаем данные
                if "posts" in state:
                    # Очищаем старые посты которые вышли за window
                    # BUG FIX #6: Use datetime.now(timezone.utc) instead of deprecated utcnow()
                    now = datetime.now(timezone.utc)
                    for sym, posts_list in state["posts"].items():
                        filtered = [(t, p) for (t, p) in posts_list if now - t <= self.window]
                        if filtered:
                            self.posts[sym] = filtered

                # Восстанавливаем rolling stats
                if "stats_mentions" in state:
                    for sym, buf_list in state["stats_mentions"].items():
                        rs = RollingStats()
                        rs.buf = deque(buf_list, maxlen=180)
                        self.stats_mentions[sym] = rs

                if "stats_authors" in state:
                    for sym, buf_list in state["stats_authors"].items():
                        rs = RollingStats()
                        rs.buf = deque(buf_list, maxlen=180)
                        self.stats_authors[sym] = rs

                if "stats_author_weight" in state:
                    for sym, buf_list in state["stats_author_weight"].items():
                        rs = RollingStats()
                        rs.buf = deque(buf_list, maxlen=180)
                        self.stats_author_weight[sym] = rs

                if "stats_eng" in state:
                    for sym, buf_list in state["stats_eng"].items():
                        rs = RollingStats()
                        rs.buf = deque(buf_list, maxlen=180)
                        self.stats_eng[sym] = rs

            except Exception as e:
                # BUG FIX #49: Log load errors for debugging
                from ..utils.logging import logger
                logger.warning(f"Failed to load hype state: {e}. Starting with clean state.")
                pass
