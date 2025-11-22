def market_score(liq_usd: float, vol_1h: float, ret_5m: float | None,
                 price_change_1h: float | None = None, spread_bps: float | None = None,
                 txns_h1: int | None = None) -> float:
    base = 0.0
    base += 0.5 * (max(0.0, vol_1h) ** 0.3)
    # BUG FIX #19: Check 'is not None' instead of truthiness to handle txns_h1=0
    # BUG FIX #39: Apply penalty for zero transactions instead of bonus
    if txns_h1 is not None:
        if txns_h1 > 0:
            base += 0.3 * (txns_h1 ** 0.3)
        else:
            base -= 0.5  # Penalty for no activity - dead token red flag
    if ret_5m is not None: base += 0.4 * ret_5m
    if price_change_1h is not None: base += 0.2 * price_change_1h
    # BUG FIX #64: Cap spread penalty to prevent unbounded negative scores
    if spread_bps is not None:
        penalty = min(10.0, 0.2 * max(0.0, spread_bps) / 100.0)
        base -= penalty
    base += 0.2 * (max(0.0, liq_usd) ** 0.2)
    return base
