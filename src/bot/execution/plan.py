from ..models import Decision, ExecutionPlan
from .gmgn_sol import WSOL, USDC, sol_to_lamports
from ..config import settings
import re
def parse_duration(s: str | None) -> int | None:
    if not s: return None
    s=str(s).strip().lower()
    m = re.match(r"^(\d+)\s*([smhdw]?)$", s)
    if not m: return None
    val = int(m.group(1)); unit = m.group(2) or "s"
    mult = {"s":1, "m":60, "h":3600, "d":86400, "w":604800}.get(unit,1)
    return val * mult
def to_execution_plan(dec: Decision, *, in_asset: str = "WSOL",
                      size_sol: float = 0.02, size_usdc: float = 20.0,
                      anti_mev: bool = True, priority_fee_sol: float | None = 0.006) -> ExecutionPlan:
    in_token = WSOL if in_asset.upper() == "WSOL" else USDC
    amount = str(sol_to_lamports(size_sol)) if in_token == WSOL else str(int(size_usdc * 10**6))
    out_token = dec.contract or dec.symbol
    return ExecutionPlan(chain="sol", side="buy" if dec.trade_proposal.action != "short" else "sell",
                         in_token=in_token, out_token=out_token, amount_in=amount,
                         slippage_pct=settings.execution.slippage_base_pct, anti_mev=anti_mev,
                         priority_fee_sol=priority_fee_sol, tip_fee_sol=None,
                         max_hold_sec=parse_duration(dec.trade_proposal.max_hold),
                         kill_switch=dec.trade_proposal.kill_switch, symbol=dec.symbol)
def to_exit_plan(symbol: str, contract: str, qty_token: float, token_decimals: int,
                 *, out_asset: str = "WSOL", slippage_base_pct: float | None = None,
                 anti_mev: bool = True, priority_fee_sol: float | None = 0.006) -> ExecutionPlan:
    out_token = WSOL if out_asset.upper()=="WSOL" else USDC
    amount = str(int(qty_token * (10**token_decimals)))
    return ExecutionPlan(chain="sol", side="sell", in_token=contract, out_token=out_token,
                         amount_in=amount, slippage_pct=slippage_base_pct or settings.execution.slippage_base_pct,
                         anti_mev=anti_mev, priority_fee_sol=priority_fee_sol, tip_fee_sol=None, symbol=symbol)
