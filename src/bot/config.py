from __future__ import annotations
import os, yaml
from pydantic import BaseModel
DEFAULT_CFG = os.environ.get("CONFIG_PATH", "config/config.yaml")

class PerplexityConf(BaseModel):
    enabled: bool = True
    model_fast: str = "sonar-small-online"
    model_final: str = "sonar-medium-online"

class OpenAIConf(BaseModel):
    api_key: str | None = None
    model_fast: str = "gpt-5-mini"
    model_final: str = "gpt-5"

class SolanaConf(BaseModel):
    private_key_b58: str | None = None
    address: str | None = None
    rpc_url: str | None = None

class ExecConf(BaseModel):
    dry_run: bool = True
    gmgn_anti_mev: bool = True
    sol_priority_fee_sol: float = 0.006
    default_input_token: str = "WSOL"
    default_trade_size_sol: float = 0.02
    default_trade_size_usdc: float = 20.0
    slippage_base_pct: float = 30.0
    split_threshold_price_impact_pct: float = 15.0
    max_splits: int = 3

class FeaturesConf(BaseModel):
    hype_window_secs: int = 900

class LoggingConf(BaseModel):
    out_dir: str = "data"

class TelegramConf(BaseModel):
    enabled: bool = False
    bot_token: str | None = None
    chat_id: str | None = None

class SourcesConf(BaseModel):
    farcaster_enabled: bool = False
    google_news_enabled: bool = True
    google_news_lang: str = "en-US"
    google_news_geo: str = "US"
    google_news_ceid: str = "US:en"
    reddit_enabled: bool = True
    reddit_subs: list[str] = ["CryptoCurrency","CryptoMarkets","solana","CryptoMoonShots"]

class RiskConf(BaseModel):
    blacklist_mints: list[str] = []
    blacklist_symbols: list[str] = []
    max_spread_bps: float = 1000.0
    min_liquidity_usd: float = 5000.0
    min_txns_h1: int = 5

class WebConf(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    api_token: str | None = None
    basic_user: str | None = "admin"
    basic_password: str | None = "admin"

class Settings(BaseModel):
    perplexity: PerplexityConf = PerplexityConf()
    openai: OpenAIConf = OpenAIConf()
    solana: SolanaConf = SolanaConf()
    execution: ExecConf = ExecConf()
    features: FeaturesConf = FeaturesConf()
    logging: LoggingConf = LoggingConf()
    telegram: TelegramConf = TelegramConf()
    sources: SourcesConf = SourcesConf()
    risk: RiskConf = RiskConf()
    web: WebConf = WebConf()

    @staticmethod
    def load(path: str = DEFAULT_CFG) -> "Settings":
        if not os.path.exists(path):
            return Settings()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return Settings(**data)

settings = Settings.load()
