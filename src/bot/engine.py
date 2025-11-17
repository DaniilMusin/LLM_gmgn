import asyncio, json
from collections import defaultdict
from .config import settings
from .adapters.jetstream import stream_bluesky
from .adapters.rss import poll_rss, poll_google_news
from .adapters.geckoterminal import trending_pools_solana
from .adapters.dexscreener import token_info_solana, search_pairs_solana
from .adapters.farcaster import poll_farcaster
from .adapters.reddit import poll_reddit_subs
from .features.hype import HypeAggregator
from .features.market import market_score
from .features.news import news_score
from .llm.router import decide
from .models import MarketSnapshot
from .signals.scorer import decision_score
from .signals.strategy import to_trade_signal
from .execution.plan import to_execution_plan, to_exit_plan
from .execution.executor import execute_sol
from .utils.logging import log_signal
from .utils.filters import is_blocklisted, fails_risk_gates
from .utils.control import get_dry_run, get_size_sol, get_size_usdc, is_source_enabled
from .utils.solana import is_valid_mint
from .utils.db import upsert_position_on_buy, get_open_positions, mark_position_check, reduce_position, get_recent_amm_pi
from .utils.alerts import send_alert
from .utils.circuit_breaker import is_circuit_open, record_trade, get_status as get_cb_status
from .utils.portfolio_risk import can_open_new_position, get_max_position_size, get_portfolio_status

class Orchestrator:
    def __init__(self):
        self.hype = HypeAggregator(window_secs=settings.features.hype_window_secs)
        self.market_cache: dict[str, MarketSnapshot] = {}
        self.news_cache: dict[str, list[dict]] = defaultdict(list)

    async def run(self):
        tasks = [self._run_bluesky(), self._run_rss(), self._run_gecko(), self._loop_decisions(),
                 self._run_positions(), self._save_hype_state(), self._cleanup_caches()]  # BUG FIX #36
        if settings.sources.google_news_enabled: tasks.append(self._run_google_news())
        if settings.sources.farcaster_enabled: tasks.append(self._run_farcaster())
        if settings.sources.reddit_enabled: tasks.append(self._run_reddit())
        await asyncio.gather(*tasks)

    async def _run_bluesky(self):
        async for post in stream_bluesky():
            if not is_source_enabled('bluesky'): continue
            self.hype.update(post)

    async def _run_farcaster(self):
        try:
            async for post in poll_farcaster(interval=20):
                if not is_source_enabled('farcaster'): continue
                self.hype.update(post)
        except Exception as e: 
            try: await send_alert(f"❌ farcaster: {e}")
            except Exception: pass

    async def _run_reddit(self):
        try:
            subs = settings.sources.reddit_subs or ["CryptoCurrency","CryptoMarkets","solana","CryptoMoonShots"]
            async for post in poll_reddit_subs(subs=subs, interval=60):
                if not is_source_enabled('reddit'): continue
                self.hype.update(post)
        except Exception as e: 
            try: await send_alert(f"❌ reddit: {e}")
            except Exception: pass

    async def _run_rss(self):
        async for item in poll_rss(interval=60):
            if not is_source_enabled('rss'): continue
            for sym in item.symbols:
                self.news_cache[sym].append({"title": item.title, "url": str(item.url)})

    async def _run_google_news(self):
        while True:
            try:
                if not is_source_enabled('google_news'):
                    await asyncio.sleep(5); continue
                queries = list({k for k in self.market_cache.keys()})[:20]
                if not queries:
                    await asyncio.sleep(60); continue
                async for item in poll_google_news(queries, hl=settings.sources.google_news_lang,
                    gl=settings.sources.google_news_geo, ceid=settings.sources.google_news_ceid, interval=300):
                    if not is_source_enabled('google_news'): break
                    for sym in list(self.market_cache.keys()):
                        if sym.upper() in (item.title or "").upper():
                            self.news_cache[sym].append({"title": item.title, "url": str(item.url)})
            except Exception as e:
                try: await send_alert(f"❌ google_news: {e}")
                except Exception: pass
            await asyncio.sleep(10)

    async def _run_gecko(self):
        while True:
            try:
                data = await trending_pools_solana(page=1)
                pools = data.get("data", [])
                for p in pools[:10]:
                    attrs = p.get("attributes", {})
                    base = attrs.get("base_token", {}) or {}
                    symbol = (base.get("symbol") or "").upper() or (attrs.get("name","")[:6] or "UNK")
                    contract = base.get("address") or attrs.get("address")
                    if not is_valid_mint(contract):
                        try:
                            sr = await search_pairs_solana(symbol)
                            pairs = sr.get("pairs") or []
                            if pairs:
                                sol_pairs = [p for p in pairs if (p.get("chainId") == "solana" or str(p.get("chainId")).lower()=="solana")]
                                best = (sol_pairs or pairs)[0]
                                contract = (best.get("baseToken") or {}).get("address") or contract
                        except Exception:
                            pass
                    if not is_valid_mint(contract): continue
                    liq = float(attrs.get("fdv_usd", 0) or 0)
                    vol1h = float(attrs.get("volume_usd", 0) or 0)
                    ret5m = None; spread_bps = None; price_change_1h = None; txns_h1 = None
                    try:
                        ds = await token_info_solana(contract)
                        pairs = ds.get("pairs") or []
                        if pairs:
                            best = max(pairs, key=lambda x: float((x.get("liquidity") or {}).get("usd", 0) or 0))
                            liq = float((best.get("liquidity") or {}).get("usd", liq) or liq)
                            vol1h = float((best.get("volume") or {}).get("h1", vol1h) or vol1h)
                            pc = best.get("priceChange") or {}
                            ret5m = float(pc.get("m5", 0) or 0) / 100.0
                            price_change_1h = float(pc.get("h1", 0) or 0) / 100.0
                            tx = (best.get("txns") or {}).get("h1") or {}
                            buys = int(tx.get("buys", 0) or 0); sells = int(tx.get("sells", 0) or 0)
                            txns_h1 = buys + sells
                            spread_bps = float(best.get("spread", best.get("priceSpread", 0)) or 0) * 100.0
                    except Exception:
                        pass
                    self.market_cache[symbol] = MarketSnapshot(symbol=symbol, contract=contract, liq_usd=liq, vol_1h=vol1h,
                        ret_5m=ret5m, price_change_1h=price_change_1h, spread_bps=spread_bps, txns_h1=txns_h1)
            except Exception:
                pass
            await asyncio.sleep(30)

    async def _loop_decisions(self):
        while True:
            # Circuit breaker check - ONE TIME before processing candidates
            if settings.risk.circuit_breaker_enabled:
                cb_open, cb_reason = is_circuit_open()
                if cb_open:
                    try: await send_alert(f"⚠️ Circuit breaker: {cb_reason}")
                    except Exception: pass
                    await asyncio.sleep(60)  # Wait 1 minute before next check
                    continue

            candidates = list(self.hype.posts.keys())[:10]
            for sym in candidates:
                hype_val, hype_meta = self.hype.hype_score(sym)
                mkt = self.market_cache.get(sym)
                if not mkt: continue
                bl, reason = is_blocklisted(sym, mkt.contract)
                if bl: continue
                fr, why = fails_risk_gates(mkt.liq_usd, mkt.txns_h1, mkt.spread_bps)
                if fr: continue
                nitems = self.news_cache.get(sym, [])
                has_confirmed = any((d in it["url"]) for it in nitems for d in ["coindesk.com","cointelegraph.com","decrypt.co"])
                nscore = news_score(has_confirmed, len(nitems))
                mscore = market_score(mkt.liq_usd, mkt.vol_1h, mkt.ret_5m, mkt.price_change_1h, mkt.spread_bps, mkt.txns_h1)
                dscore = decision_score(hype_val, mscore, nscore)
                payload = {"symbol": sym, "contract": mkt.contract, "social": {"score":hype_val, **hype_meta},
                           "news": nitems[:6], "market": mkt.model_dump(), "quick_filter": True}
                try:
                    dec = await decide(payload)
                except Exception:
                    continue
                signal = to_trade_signal(dec, dscore)
                if not signal: continue
                from .execution.plan import to_execution_plan
                plan = to_execution_plan(dec, in_asset=settings.execution.default_input_token,
                                         size_sol=get_size_sol(), size_usdc=get_size_usdc(),
                                         anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                log_signal({"symbol": sym, "decision_conf": dec.confidence, "decision_mag": dec.magnitude,
                            "score": dscore, "action": dec.trade_proposal.action, "contract": plan.out_token,
                            "amount_in": plan.amount_in, "slippage": plan.slippage_pct, "anti_mev": plan.anti_mev})
                if get_dry_run(): continue
                # Portfolio risk checks
                can_open, port_reason = can_open_new_position()
                if not can_open:
                    try: await send_alert(f"⚠️ Portfolio limit: {port_reason}")
                    except Exception: pass
                    continue
                # Adjust position size if needed
                # NOTE: For USDC input, we need approximate WSOL equivalent for risk checks
                # BUG FIX #32: Use configurable rate instead of hardcoded value
                proposed_size_wsol = get_size_sol() if settings.execution.default_input_token.upper() == "WSOL" else (get_size_usdc() / settings.execution.wsol_usdc_rate)
                adjusted_size, size_warning = get_max_position_size(proposed_size_wsol)
                if size_warning:
                    try: await send_alert(f"⚠️ {size_warning}")
                    except Exception: pass
                    # Recreate plan with adjusted size
                    if settings.execution.default_input_token.upper() == "WSOL":
                        plan = to_execution_plan(dec, in_asset=settings.execution.default_input_token,
                                                 size_sol=adjusted_size, size_usdc=get_size_usdc(),
                                                 anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                    else:
                        plan = to_execution_plan(dec, in_asset=settings.execution.default_input_token,
                                                 size_sol=get_size_sol(), size_usdc=adjusted_size * settings.execution.wsol_usdc_rate,
                                                 anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                try:
                    res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""),
                                            from_address=(settings.solana.address or ""), dry_run=False)
                    # After buy: aggregate realized qty & decimals and open/update position
                    qty = 0.0; decs = None
                    for x in res.get("results", []):
                        if x.get("realized_out") is not None:
                            qty += float(x.get("realized_out") or 0.0)
                        if x.get("decimals") is not None:
                            decs = int(x.get("decimals") or 0)
                    cost_wsol_added = float(res.get("total_in_wsol") or 0.0)
                    upsert_position_on_buy(symbol=sym, contract=plan.out_token, qty_added=qty, cost_wsol_added=cost_wsol_added,
                                           max_hold_sec=plan.max_hold_sec, decimals=decs, entry_txns_h1=(mkt.txns_h1 or 0),
                                           owner_address=(settings.solana.address or ""), kill_switch=plan.kill_switch)
                    try: await send_alert(f"✅ Buy {sym} opened/added qty={qty:.6f}")
                    except Exception: pass
                except Exception as e:
                    # Record entry failure to circuit breaker - at minimum we lost gas fees
                    if settings.risk.circuit_breaker_enabled:
                        # Estimate gas loss: ~0.001 WSOL for failed transaction
                        estimated_gas_loss = -0.001
                        record_trade(estimated_gas_loss, plan.out_token)
                    try: await send_alert(f"❌ EXEC buy: {e}")
                    except Exception: pass
            await asyncio.sleep(15)

    async def _run_positions(self):
        from .execution.gmgn_sol import WSOL, LAMPORTS, gmgn_get_route_sol

        def _record_exit_to_cb(invested_wsol: float, realized_wsol: float, sell_qty: float, total_qty: float, contract: str):
            """Helper to record exit result to circuit breaker."""
            if not settings.risk.circuit_breaker_enabled:
                return
            # Calculate P/L for this exit
            invested_portion = invested_wsol * (sell_qty / max(1e-12, total_qty))
            profit_loss = realized_wsol - invested_portion
            record_trade(profit_loss, contract)

        while True:
            try:
                open_pos = get_open_positions()
                for pos in open_pos:
                    symbol = pos["symbol"]; contract = pos["contract"]
                    qty = float(pos["qty"] or 0.0)
                    if qty <= 1e-12: continue
                    invested = float(pos["invested_wsol"] or 0.0)
                    decimals = int(pos["decimals"] or 9)
                    max_hold_sec = int(pos["max_hold_sec"] or 0)
                    opened_at = pos["opened_at"]
                    # Mark: quote token->WSOL
                    exp_wsol = 0.0
                    quote_failed = False
                    try:
                        amt = int(qty * (10**decimals))
                        r = await gmgn_get_route_sol(contract, WSOL, amt, from_addr=(settings.solana.address or ""), slippage_pct=settings.execution.slippage_base_pct)
                        q = (r.get("data") or {}).get("quote", {}) or {}
                        for k_ in ["outAmount","expectedOut","amountOut","out_amount"]:
                            if k_ in q:
                                try: exp_wsol = float(q.get(k_)) / LAMPORTS; break
                                except Exception: pass
                        if exp_wsol <= 0:
                            quote_failed = True
                    except Exception as e:
                        quote_failed = True
                        try: await send_alert(f"⚠️ Quote error for {symbol}: {e}")
                        except Exception: pass

                    # BUG FIX #28: Track quote failures and emergency exit after 5 consecutive failures
                    meta = {}
                    try:
                        meta = json.loads(pos["meta_json"] or "{}")
                    except Exception:
                        meta = {}

                    if quote_failed:
                        quote_failures = meta.get("quote_failures", 0) + 1
                        meta["quote_failures"] = quote_failures

                        # Emergency exit after 5 consecutive failures
                        if quote_failures >= 5:
                            from ..utils.db import update_position_meta
                            update_position_meta(pos["id"], meta)
                            try:
                                # Force close position with market order (no quote check)
                                sell_qty = qty
                                plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                                    slippage_base_pct=settings.execution.slippage_base_pct * 2,  # Double slippage for emergency
                                                    anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                                res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                                realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                                reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=None, realized_out_wsol=realized,
                                              slippage_pct=None, amm_pi_pct=None,
                                              tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None),
                                              reason="emergency_quote_failure")
                                _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                                await send_alert(f"🚨 Emergency exit {symbol} after {quote_failures} quote failures")
                            except Exception as e:
                                logger.error(f"Emergency exit failed for {symbol}: {e}")
                            continue

                        # Not yet at emergency threshold, save and skip
                        from ..utils.db import update_position_meta
                        update_position_meta(pos["id"], meta)
                        continue
                    else:
                        # Quote succeeded, reset failure counter
                        if meta.get("quote_failures", 0) > 0:
                            meta["quote_failures"] = 0
                            from ..utils.db import update_position_meta
                            update_position_meta(pos["id"], meta)

                    current_ret = (exp_wsol - invested) / max(1e-9, invested) if invested>0 else 0.0
                    # HWM update
                    hwm_wsol = float(pos["hwm_wsol"] or 0.0)
                    new_hwm_wsol = max(hwm_wsol, exp_wsol)
                    high_ret = (new_hwm_wsol - invested) / max(1e-9, invested) if invested>0 else 0.0
                    steps = int(max(0.0, high_ret) // 0.05)
                    trail_pct = max(0.08, 0.12 - 0.02 * steps)
                    drawdown = (new_hwm_wsol - exp_wsol) / max(1e-9, new_hwm_wsol) if new_hwm_wsol>0 else 0.0
                    tp1_done = bool(pos["tp1_done"]); tp2_done = bool(pos["tp2_done"])
                    # Market snapshot
                    m = self.market_cache.get(symbol)

                    # Pre-calculate market stress conditions
                    stress_spread = m and m.spread_bps is not None and m.spread_bps > 1.5 * settings.risk.max_spread_bps
                    stress_txns = m and m.txns_h1 is not None and int(pos["entry_txns_h1"] or 0) > 0 and m.txns_h1 < 0.5 * int(pos["entry_txns_h1"])
                    recent_min_pi = get_recent_amm_pi(contract, minutes=60) or 0.0
                    stress_amm = recent_min_pi < -8.0

                    # Hype downgrade - OPTIMIZED: Only check every 5 minutes to reduce LLM costs
                    from datetime import datetime as _dt, timezone as _tz
                    last_check_ts = pos.get("last_check_ts")
                    should_check_downgrade = True
                    if last_check_ts:
                        try:
                            last_check = _dt.fromisoformat(last_check_ts)
                            # BUG FIX #22: Replace deprecated utcnow() with now(timezone.utc)
                            if (_dt.now(_tz.utc) - last_check).total_seconds() < 300:  # 5 minutes
                                should_check_downgrade = False
                        except Exception:
                            pass

                    downgrade = False
                    if should_check_downgrade:
                        # BUG FIX #24: Update last_check_ts BEFORE LLM call to prevent race condition
                        mark_position_check(pos["id"], None, None, None, None)  # Updates last_check_ts

                        hype_val, hype_meta = self.hype.hype_score(symbol)
                        z_sum = (hype_meta.get("z_m",0)+hype_meta.get("z_a",0)+hype_meta.get("z_e",0))
                        nitems = self.news_cache.get(symbol, [])
                        has_confirmed = any((d in it["url"]) for it in nitems for d in ["coindesk.com","cointelegraph.com","decrypt.co"])
                        nscore = news_score(has_confirmed, len(nitems))
                        mscore = market_score(m.liq_usd if m else 0.0, m.vol_1h if m else 0.0, m.ret_5m if m else 0.0, m.price_change_1h if m else 0.0, m.spread_bps if m else None, m.txns_h1 if m else None)
                        dscore = decision_score(hype_val, mscore, nscore)
                        try:
                            payload = {"symbol": symbol, "contract": contract, "social": {"score":hype_val, **hype_meta}, "news": nitems[:6], "market": m.model_dump() if m else {}, "quick_filter": True}
                            dec2 = await decide(payload)
                            if (dscore < 0.0 or dec2.direction == "down" or dec2.trade_proposal.action in ("flat","short")) and (z_sum < 0):
                                downgrade = True
                        except Exception:
                            pass
                    # Load kill switches
                    kills = set()
                    try:
                        meta = json.loads(pos["meta_json"] or "{}"); kills = set([k.lower() for k in meta.get("kill_switch", [])])
                    except Exception:
                        kills = set()
                    # --- Exits
                    # Kill-switch -> full
                    if any(k in kills for k in ("rug","lp_pull","honeypot","dev_minted_more")):
                        sell_qty = qty
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=exp_wsol, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason="kill_switch")
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                        try: await send_alert(f"⛔ Kill-switch exit {symbol}")
                        except Exception: pass
                        continue
                    # Time stop
                    if max_hold_sec and opened_at:
                        from datetime import datetime as _dt, timezone as _tz
                        t0 = _dt.fromisoformat(opened_at)
                        # BUG FIX #22: Replace deprecated utcnow() with now(timezone.utc)
                        if (_dt.now(_tz.utc) - t0).total_seconds() >= max_hold_sec:
                            sell_qty = qty
                            plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                                slippage_base_pct=settings.execution.slippage_base_pct,
                                                anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                            res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                            realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                            reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=exp_wsol, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason="time_stop")
                            _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                            try: await send_alert(f"⏰ Time-stop exit {symbol}")
                            except Exception: pass
                            continue
                    # TP ladder
                    if not tp1_done and current_ret >= 0.15:
                        sell_qty = qty * 0.30
                        expected_out_portion = exp_wsol * (sell_qty / qty)  # Correct proportion
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=expected_out_portion, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason="tp1")
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)  # Record to CB
                        tp1_done = True
                        # BUG FIX #16: Update local variables after partial exit
                        qty = qty - sell_qty
                        exp_wsol = exp_wsol - expected_out_portion  # Update exp_wsol for remaining qty
                        invested_portion = invested * (sell_qty / (qty + sell_qty))  # Invested for sold portion
                        invested = invested - invested_portion  # Update invested for remaining
                        # BUG FIX #31: Prevent negative values from rounding errors
                        qty = max(0.0, qty)
                        exp_wsol = max(0.0, exp_wsol)
                        invested = max(0.0, invested)
                        current_ret = (exp_wsol - invested) / max(1e-9, invested) if invested > 0 else 0.0  # Recalculate
                        # BUG FIX #23: Persist tp1_done flag immediately to prevent duplicate TP1 execution
                        mark_position_check(pos["id"], None, None, tp1_done, None)
                        try: await send_alert(f"🎯 TP1 exit 30% {symbol}")
                        except Exception: pass
                    if not tp2_done and current_ret >= 0.35:
                        sell_qty = qty * 0.30  # 30% of REMAINING qty
                        # BUG FIX #10: Use correct proportion calculation (same as TP1)
                        expected_out_portion = exp_wsol * (sell_qty / qty)
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=expected_out_portion, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason="tp2")
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)  # Record to CB with correct qty
                        tp2_done = True
                        # BUG FIX #16: Update local variables after partial exit
                        qty = qty - sell_qty
                        exp_wsol = exp_wsol - expected_out_portion  # Update exp_wsol for remaining qty
                        invested_portion = invested * (sell_qty / (qty + sell_qty))  # Invested for sold portion
                        invested = invested - invested_portion  # Update invested for remaining
                        # BUG FIX #31: Prevent negative values from rounding errors
                        qty = max(0.0, qty)
                        exp_wsol = max(0.0, exp_wsol)
                        invested = max(0.0, invested)
                        current_ret = (exp_wsol - invested) / max(1e-9, invested) if invested > 0 else 0.0  # Recalculate
                        # BUG FIX #23: Persist tp2_done flag immediately to prevent duplicate TP2 execution
                        mark_position_check(pos["id"], None, None, None, tp2_done)
                        try: await send_alert(f"🎯 TP2 exit 30% {symbol}")
                        except Exception: pass
                    # Trailing stop (remaining)
                    if new_hwm_wsol > 0 and drawdown >= trail_pct:
                        sell_qty = qty
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=exp_wsol, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason="trailing_stop")
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                        try: await send_alert(f"🪓 Trailing stop exit {symbol}")
                        except Exception: pass
                        continue
                    # Downgrade exit (half/full)
                    if downgrade:
                        if current_ret <= 0.0 or dscore < -0.5:
                            sell_qty = qty
                            reason = "downgrade_full"
                        else:
                            sell_qty = qty * 0.5
                            reason = "downgrade_half"
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=exp_wsol*(sell_qty/qty), realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason=reason)
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                        try: await send_alert(f"📉 Downgrade exit {symbol} ({reason})")
                        except Exception: pass
                        # continue to next pos
                        continue
                    # Market stress (spread/txns/amm) - Use pre-calculated conditions
                    if stress_spread or stress_txns or stress_amm:
                        sell_qty = qty
                        reason = "stress_spread" if stress_spread else ("stress_txns" if stress_txns else "stress_amm_pi")
                        plan = to_exit_plan(symbol, contract, sell_qty, decimals, out_asset=settings.execution.default_input_token,
                                            slippage_base_pct=settings.execution.slippage_base_pct,
                                            anti_mev=settings.execution.gmgn_anti_mev, priority_fee_sol=settings.execution.sol_priority_fee_sol)
                        res = await execute_sol(plan, payer_b58=(settings.solana.private_key_b58 or ""), from_address=(settings.solana.address or ""), dry_run=False)
                        realized = sum((x.get("realized_out") or 0) for x in res.get("results", []))
                        reduce_position(pos["id"], qty_sold=sell_qty, expected_out_wsol=exp_wsol, realized_out_wsol=realized, slippage_pct=None, amm_pi_pct=None, tx=(res.get("results",[{}])[0].get("tx") if res.get("results") else None), reason=reason)
                        _record_exit_to_cb(invested, realized, sell_qty, qty, contract)
                        try: await send_alert(f"⚠️ Market-stress exit {symbol} ({reason})")
                        except Exception: pass
                        continue  # Skip to next position after stress exit
                    # persist marks/state
                    mark_position_check(pos["id"], new_hwm_wsol, high_ret, tp1_done, tp2_done)
            except Exception as e:
                try: await send_alert(f"❌ positions: {e}")
                except Exception: pass
            await asyncio.sleep(15)

    async def _save_hype_state(self):
        """Периодически сохраняет состояние hype aggregator."""
        while True:
            try:
                await asyncio.sleep(300)  # Сохраняем каждые 5 минут
                self.hype.save_state()
            except Exception as e:
                # BUG FIX #35: Log errors instead of silent failures
                logger.error(f"Failed to save hype state: {e}")
                try:
                    await send_alert(f"⚠️ Hype state save error: {e}")
                except:
                    pass

    async def _cleanup_caches(self):
        """BUG FIX #36: Периодически очищает старые записи из кешей для предотвращения утечки памяти."""
        while True:
            try:
                await asyncio.sleep(3600)  # Очищаем каждый час
                # Оставляем только последние 100 символов в market_cache
                if len(self.market_cache) > 100:
                    # Удаляем старые записи, оставляем 100 последних
                    sorted_keys = sorted(self.market_cache.keys())
                    for key in sorted_keys[:-100]:
                        del self.market_cache[key]
                    logger.info(f"Cleaned market_cache, kept 100 most recent entries")

                # Очищаем news_cache для символов без открытых позиций
                from ..utils.db import get_open_positions
                open_symbols = {pos["symbol"] for pos in get_open_positions()}
                symbols_to_remove = [sym for sym in self.news_cache.keys() if sym not in open_symbols and len(self.news_cache[sym]) > 50]
                for sym in symbols_to_remove:
                    del self.news_cache[sym]
                if symbols_to_remove:
                    logger.info(f"Cleaned news_cache, removed {len(symbols_to_remove)} stale entries")
            except Exception as e:
                logger.error(f"Cache cleanup error: {e}")
