from __future__ import annotations
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Literal, Optional, Dict
from datetime import datetime

class SocialPost(BaseModel):
    platform: Literal["bluesky","reddit","farcaster"]
    post_id: str
    author_handle: Optional[str] = None
    author_followers: Optional[int] = None
    verified: Optional[bool] = None
    created_at: datetime
    text: str
    url: Optional[HttpUrl] = None
    symbols: List[str] = Field(default_factory=list)
    lang: Optional[str] = None
    engagement: Dict[str, int] = Field(default_factory=dict)

class NewsItem(BaseModel):
    source: str
    title: str
    url: HttpUrl
    published_at: datetime
    symbols: List[str] = Field(default_factory=list)

class MarketSnapshot(BaseModel):
    symbol: str
    contract: Optional[str] = None
    network: Optional[str] = "solana"
    liq_usd: float = 0.0
    vol_1h: float = 0.0
    txns_h1: Optional[int] = None
    ret_5m: Optional[float] = None
    price_change_1h: Optional[float] = None
    spread_bps: Optional[float] = None

EventType = Literal["exchange_listing","partnership_product","security_incident","regulatory_legal","network_status","unlock_supply","shill","other"]

class SourceRef(BaseModel):
    url: HttpUrl
    domain: str
    trust: Literal["high","med","low"] = "med"

class TradeProposal(BaseModel):
    action: Literal["long","short","flat"] = "long"
    weight: float = 0.5
    max_hold: str = "90m"
    kill_switch: List[str] = Field(default_factory=list)

class Decision(BaseModel):
    symbol: str
    contract: Optional[str] = None
    event_type: List[EventType] = Field(default_factory=lambda: ["other"])
    direction: Literal["up","down","neutral"] = "neutral"
    horizon: Literal["intra","1d","1w"] = "intra"
    confidence: float = 0.0
    novelty: float = 0.0
    magnitude: float = 0.0
    sources: List[SourceRef] = Field(default_factory=list)
    social_summary: Dict[str, object] = Field(default_factory=dict)
    market_checks: Dict[str, object] = Field(default_factory=dict)
    trade_proposal: TradeProposal = Field(default_factory=TradeProposal)

class ExecutionPlan(BaseModel):
    chain: Literal["sol"]
    side: Literal["buy","sell"] = "buy"
    in_token: str
    out_token: str
    amount_in: str
    slippage_pct: float | None = None
    anti_mev: bool = False
    priority_fee_sol: float | None = None
    tip_fee_sol: float | None = None
    # exit/management
    max_hold_sec: int | None = None
    kill_switch: list[str] = Field(default_factory=list)
    symbol: str | None = None
