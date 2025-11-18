from __future__ import annotations
import os, yaml
from pydantic import BaseModel, field_validator
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
    # BUG FIX #32: Make WSOL/USDC rate configurable instead of hardcoded
    wsol_usdc_rate: float = 150.0  # Approximate USDC per WSOL for risk calculations

    # BUG FIX #21: Add config validation
    @field_validator('slippage_base_pct')
    @classmethod
    def validate_slippage(cls, v: float) -> float:
        if v <= 0 or v > 100:
            raise ValueError(f"slippage_base_pct must be between 0 and 100, got {v}")
        return v

    @field_validator('max_splits')
    @classmethod
    def validate_max_splits(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError(f"max_splits must be between 1 and 10, got {v}")
        return v

    # BUG FIX #61: Add validation to prevent division by zero
    @field_validator('wsol_usdc_rate')
    @classmethod
    def validate_wsol_usdc_rate(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"wsol_usdc_rate must be positive, got {v}")
        return v

    @field_validator('split_threshold_price_impact_pct')
    @classmethod
    def validate_split_threshold(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"split_threshold_price_impact_pct must be non-negative, got {v}")
        return v

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
    # Circuit breaker settings
    circuit_breaker_enabled: bool = True
    circuit_breaker_window: int = 20  # количество последних сделок для анализа
    circuit_breaker_min_trades: int = 5  # минимум сделок для активации
    circuit_breaker_loss_threshold_pct: float = 0.7  # 70% убыточных сделок
    circuit_breaker_max_drawdown_wsol: float = 0.5  # максимальный drawdown в WSOL
    circuit_breaker_cooldown_hours: int = 4  # часы до автоматического сброса
    # Portfolio risk management
    max_open_positions: int = 5  # максимум открытых позиций одновременно
    max_portfolio_risk_wsol: float = 2.0  # максимальный суммарный риск портфеля
    max_position_size_pct: float = 0.3  # максимум 30% портфеля на одну позицию

    # BUG FIX #21: Add config validation
    @field_validator('circuit_breaker_loss_threshold_pct')
    @classmethod
    def validate_loss_threshold(cls, v: float) -> float:
        if v <= 0 or v > 1.0:
            raise ValueError(f"circuit_breaker_loss_threshold_pct must be between 0 and 1.0, got {v}")
        return v

    @field_validator('max_position_size_pct')
    @classmethod
    def validate_position_size(cls, v: float) -> float:
        if v <= 0 or v > 1.0:
            raise ValueError(f"max_position_size_pct must be between 0 and 1.0, got {v}")
        return v

    @field_validator('max_open_positions')
    @classmethod
    def validate_max_positions(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"max_open_positions must be at least 1, got {v}")
        return v

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
