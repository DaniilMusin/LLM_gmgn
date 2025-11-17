def news_score(has_confirmed: bool, mentions: int) -> float:
    return (0.8 if has_confirmed else 0.0) + 0.3 * min(3.0, mentions**0.5)
