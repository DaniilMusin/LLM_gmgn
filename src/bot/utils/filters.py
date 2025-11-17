from __future__ import annotations
from ..config import settings
def is_blocklisted(symbol: str | None, mint: str | None) -> tuple[bool,str]:
    s=(symbol or "").upper(); m=(mint or "")
    if m and any(m.lower()==x.lower() for x in settings.risk.blacklist_mints): return True, "mint in blacklist"
    if s and any(pat.upper() in s for pat in settings.risk.blacklist_symbols): return True, "symbol in blacklist"
    return False, ""
def fails_risk_gates(liq_usd: float | None, txns_h1: int | None, spread_bps: float | None) -> tuple[bool, str]:
    if liq_usd is not None and liq_usd < settings.risk.min_liquidity_usd: return True, f"liq_usd<{settings.risk.min_liquidity_usd}"
    if txns_h1 is not None and txns_h1 < settings.risk.min_txns_h1: return True, f"txns_h1<{settings.risk.min_txns_h1}"
    if spread_bps is not None and spread_bps > settings.risk.max_spread_bps: return True, f"spread_bps>{settings.risk.max_spread_bps}"
    return False, ""
