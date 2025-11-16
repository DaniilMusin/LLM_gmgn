def market_score(liq_usd: float, vol_1h: float, ret_5m: float | None,
                 price_change_1h: float | None = None, spread_bps: float | None = None,
                 txns_h1: int | None = None) -> float:
    base = 0.0
    base += 0.5 * (max(0.0, vol_1h) ** 0.3)
    if txns_h1: base += 0.3 * (max(1.0, txns_h1) ** 0.3)
    if ret_5m is not None: base += 0.4 * ret_5m
    if price_change_1h is not None: base += 0.2 * price_change_1h
    if spread_bps is not None: base -= 0.2 * max(0.0, spread_bps) / 100.0
    base += 0.2 * (max(0.0, liq_usd) ** 0.2)
    return base
