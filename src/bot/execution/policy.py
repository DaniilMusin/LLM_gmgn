from dataclasses import dataclass
@dataclass
class RouteChoice: idx:int; out_usd:float; price_impact:float; score:float
def dynamic_slippage(base_pct: float, price_impact_pct: float, has_tax: bool) -> float:
    s = max(base_pct, min(50.0, base_pct + 2.0*price_impact_pct))
    if has_tax: s = min(50.0, max(s, 10.0))
    return s
