def decision_score(hype: float, mkt: float, news: float) -> float:
    # BUG FIX #18: Normalize weights to sum to 1.0
    # Old: 0.5 + 0.4 + 0.3 = 1.2 (unnormalized)
    # New: 0.417 + 0.333 + 0.25 = 1.0 (normalized, maintaining relative importance)
    return 0.417*hype + 0.333*mkt + 0.25*news
