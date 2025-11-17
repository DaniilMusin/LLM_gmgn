from ..models import ExecutionPlan
from .gmgn_sol import gmgn_get_route_sol, sol_sign_tx_base64, gmgn_send_tx_sol, gmgn_poll_status
from ..config import settings
from ..utils.alerts import send_alert
from ..utils.db import save_quote, save_trade
from ..utils.amm_decode import estimate_pool_price_impact
import httpx, math
async def _fetch_solana_tx(sig: str) -> dict | None:
    url = settings.solana.rpc_url
    if not url: return None
    payload = {"jsonrpc":"2.0","id":1,"method":"getTransaction","params":[sig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}]}
    try:
        async with httpx.AsyncClient(timeout=20) as cli:
            r = await cli.post(url, json=payload); r.raise_for_status(); return r.json().get("result")
    except Exception: return None
def _extract_owner_balances(meta: dict, owner: str, mint: str) -> tuple[float,float,int]:
    pre = meta.get("preTokenBalances") or []; post = meta.get("postTokenBalances") or []
    def pick(balances):
        for b in balances:
            try:
                if b.get("owner") == owner and b.get("mint") == mint:
                    ui = b.get("uiTokenAmount") or {}; return float(ui.get("uiAmount", 0) or 0), int(ui.get("decimals", 0) or 0)
            except Exception: continue
        return 0.0, 0
    a0, dec0 = pick(pre); a1, dec1 = pick(post); return a0, a1, max(dec0, dec1)
async def execute_sol(plan: ExecutionPlan, *, payer_b58: str, from_address: str, dry_run: bool = True) -> dict:
    # initial route for price impact & potential split calc
    route0 = await gmgn_get_route_sol(plan.in_token, plan.out_token, int(plan.amount_in), from_address,
                                      plan.slippage_pct or settings.execution.slippage_base_pct,
                                      is_anti_mev=plan.anti_mev, fee_sol=plan.priority_fee_sol)
    q0 = route0.get("data",{}).get("quote",{}) or {}
    pi = float(q0.get("priceImpact", 0) or q0.get("price_impact", 0) or 0)
    splits = [int(plan.amount_in)]
    if pi > settings.execution.split_threshold_price_impact_pct and settings.execution.max_splits > 1:
        k = min(settings.execution.max_splits, max(2, math.ceil(pi / settings.execution.split_threshold_price_impact_pct)))
        part = int(int(plan.amount_in) / k); splits = [part]*(k-1) + [int(plan.amount_in) - part*(k-1)]
    results = []; total_in_wsol = 0.0; failed_splits = []  # BUG FIX #8: Track failed splits
    for idx, amt in enumerate(splits, start=1):
        r = await gmgn_get_route_sol(plan.in_token, plan.out_token, int(amt), from_address,
                                     plan.slippage_pct or settings.execution.slippage_base_pct,
                                     is_anti_mev=plan.anti_mev, fee_sol=plan.priority_fee_sol)
        d = r.get("data",{}); unsigned = d.get("raw_tx",{}).get("swapTransaction"); last_h = d.get("raw_tx",{}).get("lastValidBlockHeight")
        q = d.get("quote",{}); exp_out = None
        for k_ in ["outAmount","expectedOut","amountOut","out_amount"]:
            if k_ in q:
                try: exp_out = float(q[k_]); break
                except Exception: pass
        pi_local = float(q.get("priceImpact", q.get("price_impact", 0)) or 0)
        # persist quote
        quote_id = save_quote(symbol=(plan.symbol or plan.out_token), contract=(plan.out_token if plan.side=='buy' else plan.in_token),
                              in_token=plan.in_token, out_token=plan.out_token, in_amount=str(amt),
                              slippage=plan.slippage_pct, anti_mev=plan.anti_mev, priority_fee=plan.priority_fee_sol,
                              quote=q, price_impact=pi_local, expected_out=exp_out, route_json=d)
        if dry_run:
            results.append({"dry_run": True, "split": idx, "quote_id": quote_id, "quote": q, "last_valid_height": last_h, "expected_out": exp_out})
            continue
        # sign & send
        try:
            signed_b64 = sol_sign_tx_base64(unsigned, payer_b58)
            sent = await gmgn_send_tx_sol(signed_b64, anti_mev=plan.anti_mev)
            txsig = sent.get("data",{}).get("hash")
            status = await gmgn_poll_status(txsig, last_h)
            realized = None; dec = 0; amm_pi = None
            try:
                txres = await _fetch_solana_tx(txsig)
                if txres and txres.get("meta"):
                    # realized_out measured on out_token (buy: acquired token; sell: WSOL received)
                    a0,a1,dec = _extract_owner_balances(txres["meta"], from_address, plan.out_token)
                    # BUG FIX #12: Don't mask negative realized_out, but log warning
                    realized = a1 - a0
                    if realized < 0:
                        try:
                            await send_alert(f"⚠️ Negative realized_out: {realized} for tx {txsig}")
                        except Exception: pass
                        realized = 0.0  # Still cap at zero for downstream logic
                    amm_pi, _det = estimate_pool_price_impact(txres["meta"], trader_owner=from_address)
                else:
                    # No meta available, assume failed quote
                    realized = 0.0
            except Exception as e:
                # BUG FIX #37: Log errors and set realized to 0 on failure
                logger.error(f"Failed to get tx details for {txsig}: {e}")
                realized = 0.0  # Assume worst case for stats
            slip_pct = None
            if exp_out is not None and realized is not None:
                try: slip_pct = (exp_out - realized) / max(1e-9, exp_out) * 100.0
                except Exception: pass
            save_trade(quote_id=quote_id, tx=txsig, split=idx, status=status.get("data"), realized_out=realized, slippage_pct=slip_pct, amm_pi_pct=amm_pi, side=plan.side, contract=(plan.out_token if plan.side=='buy' else plan.in_token))
            results.append({"tx": txsig, "status": status.get("data"), "split": idx, "expected_out": exp_out, "realized_out": realized, "slippage_pct": slip_pct, "amm_pi_pct": amm_pi, "decimals": dec})
            # BUG FIX #7: Use WSOL constant instead of hardcoded substring check
            from .gmgn_sol import WSOL, LAMPORTS
            if plan.in_token == WSOL:
                total_in_wsol += (amt / LAMPORTS)
        except Exception as e:
            # BUG FIX #8: Track split failures
            failed_splits.append((idx, str(e)))
            results.append({"error": str(e), "split": idx, "expected_out": exp_out})

    # BUG FIX #8: Alert if some splits failed
    if failed_splits and len(failed_splits) < len(splits):
        try:
            await send_alert(f"⚠️ Partial split failure: {len(failed_splits)}/{len(splits)} splits failed for {plan.symbol or plan.out_token}")
        except Exception: pass

    return {"results": results, "splits": len(splits), "pi0": pi, "total_in_wsol": total_in_wsol, "failed_splits": len(failed_splits)}
