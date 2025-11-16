from __future__ import annotations
from typing import Tuple, Optional
def _sum_balances(balances: list[dict], owner_filter: str | None = None):
    by_mint = {}
    for b in balances or []:
        owner = b.get("owner") or ""
        if owner_filter and owner == owner_filter:
            continue
        mint = b.get("mint")
        ui = b.get("uiTokenAmount") or {}
        amt = float(ui.get("uiAmount", 0) or 0)
        by_mint.setdefault(mint, 0.0); by_mint[mint] += amt
    return by_mint
def estimate_pool_price_impact(meta: dict, trader_owner: str | None = None) -> Tuple[Optional[float], dict]:
    pre = meta.get("preTokenBalances") or []; post = meta.get("postTokenBalances") or []
    pre_by = _sum_balances(pre, trader_owner); post_by = _sum_balances(post, trader_owner)
    deltas = []; [deltas.append((mint, (post_by.get(mint,0.0)-pre_by.get(mint,0.0)))) for mint in set(pre_by)|set(post_by)]
    deltas_sorted = sorted(deltas, key=lambda x: abs(x[1]), reverse=True)[:2]
    if len(deltas_sorted) < 2: return None, {"reason": "not enough deltas"}
    (mint_a, da), (mint_b, db) = deltas_sorted
    ra_in = pre_by.get(mint_a, 0.0); rb_out = pre_by.get(mint_b, 0.0)
    if ra_in <= 0 or rb_out <= 0: return None, {"reason": "invalid reserves", "pre": pre_by}
    price_before = rb_out / ra_in
    ra_in_after = post_by.get(mint_a, 0.0); rb_out_after = post_by.get(mint_b, 0.0)
    if ra_in_after <= 0 or rb_out_after <= 0: return None, {"reason": "invalid reserves after", "post": post_by}
    price_after = rb_out_after / ra_in_after
    pi = (price_after - price_before) / price_before * 100.0
    return pi, {"mints":[mint_a,mint_b],"delta":[da,db],"price_before":price_before,"price_after":price_after}
def decode_exact_pool_pi(meta: dict, trader_owner: str | None = None):
    return estimate_pool_price_impact(meta, trader_owner)
