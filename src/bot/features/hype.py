from collections import defaultdict, deque
from math import sqrt
from datetime import datetime, timedelta
from ..models import SocialPost
from ..utils import authors
import re
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
    def __init__(self, window_secs=900):
        self.window = timedelta(seconds=window_secs)
        self.posts = defaultdict(list)
        self.stats_mentions = defaultdict(RollingStats)
        self.stats_authors  = defaultdict(RollingStats)
        self.stats_author_weight = defaultdict(RollingStats)
        self.stats_eng      = defaultdict(RollingStats)
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
