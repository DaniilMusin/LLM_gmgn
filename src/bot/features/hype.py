from collections import defaultdict, deque
from math import sqrt
from datetime import datetime, timedelta
from ..models import SocialPost
from ..utils import authors
import re, os, pickle
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
        now = datetime.utcnow()
        for sym in post.symbols:
            self.posts[sym].append((now, post))
            self.posts[sym] = [(t,p) for (t,p) in self.posts[sym] if now - t <= self.window]
    def hype_score(self, symbol: str):
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
                "saved_at": datetime.utcnow().isoformat()
            }
            with open(self._state_path, "wb") as f:
                pickle.dump(state, f)
        except Exception as e:
            # Не падаем если не удалось сохранить
            pass

    def load_state(self):
        """Загружает состояние HypeAggregator из файла."""
        try:
            if not os.path.exists(self._state_path):
                return
            with open(self._state_path, "rb") as f:
                state = pickle.load(f)

            # Восстанавливаем данные
            if "posts" in state:
                # Очищаем старые посты которые вышли за window
                now = datetime.utcnow()
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
            # Не падаем если не удалось загрузить
            pass
