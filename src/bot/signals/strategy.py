from ..models import Decision
def to_trade_signal(dec: Decision, score: float):
    if dec.trade_proposal.action == "flat": return None
    w = max(0.0, min(1.0, dec.trade_proposal.weight)) * min(1.0, 0.5 + 0.5*max(0.0, score))
    return {"action": dec.trade_proposal.action, "weight": round(w,4), "event": dec.event_type,
            "confidence": dec.confidence, "magnitude": dec.magnitude, "sources": [s.url for s in dec.sources]}
