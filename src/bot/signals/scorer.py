def decision_score(hype: float, mkt: float, news: float) -> float:
    return 0.5*hype + 0.4*mkt + 0.3*news
