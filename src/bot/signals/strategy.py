from ..models import Decision
def to_trade_signal(dec: Decision, score: float):
    if dec.trade_proposal.action == "flat": return None
    # BUG FIX #20: Allow weight to go to 0 for negative scores
    # Old: min(1.0, 0.5 + 0.5*max(0.0, score)) -> min weight was 0.5 even for negative scores
    # New: max(0.0, min(1.0, 0.5 + 0.5*score)) -> allows 0.0 for score=-1, 1.0 for score=1
    score_factor = max(0.0, min(1.0, 0.5 + 0.5*score))
    w = max(0.0, min(1.0, dec.trade_proposal.weight)) * score_factor
    return {"action": dec.trade_proposal.action, "weight": round(w,4), "event": dec.event_type,
            "confidence": dec.confidence, "magnitude": dec.magnitude, "sources": [s.url for s in dec.sources]}
