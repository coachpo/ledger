from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings, get_settings

PredictionMarketVenue = Literal["polymarket", "kalshi"]
MarketSentimentIndicator = Literal["fear_greed"]

PREDICTION_MARKET_VENUES: tuple[PredictionMarketVenue, ...] = ("polymarket", "kalshi")
MARKET_SENTIMENT_PROVIDER_KEY: MarketSentimentIndicator = "fear_greed"
MARKET_SENTIMENT_SOURCE_URL = "https://www.cnn.com/markets/fear-and-greed"

DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE = False
DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE = False
DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY = (
    "Phase 1 uses Digital Oracle provider wrappers; do not vendor "
    "digital-oracle or require yfinance."
)

EDGAR_CONTACT_EMAIL_SETTING = "DIGITAL_ORACLE_EDGAR_CONTACT_EMAIL"
EDGAR_CONTACT_EMAIL_MISSING_CODE = "digital_oracle_edgar_contact_email_missing"
EDGAR_CONTACT_EMAIL_MISSING_MESSAGE = (
    "SEC EDGAR provider is not configured. Set "
    f"{EDGAR_CONTACT_EMAIL_SETTING} in backend configuration before using "
    "signaldeck.digital_oracle.sec_filings.lookup."
)


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderConfig:
    prediction_markets_enabled: bool
    sec_filings_enabled: bool
    market_sentiment_enabled: bool
    prediction_markets_default_item_limit: int
    sec_filings_default_item_limit: int
    provider_timeout_seconds: float
    edgar_contact_email: str | None
    requires_vendored_package: bool = DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE
    requires_yfinance: bool = DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE
    provider_boundary: str = DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY

    @property
    def prediction_market_venues(self) -> tuple[PredictionMarketVenue, ...]:
        return PREDICTION_MARKET_VENUES

    @property
    def market_sentiment_indicator(self) -> MarketSentimentIndicator:
        return MARKET_SENTIMENT_PROVIDER_KEY


def get_digital_oracle_provider_config(
    settings: Settings | None = None,
) -> DigitalOracleProviderConfig:
    resolved_settings = settings or get_settings()
    return DigitalOracleProviderConfig(
        prediction_markets_enabled=(resolved_settings.digital_oracle_prediction_markets_enabled),
        sec_filings_enabled=resolved_settings.digital_oracle_sec_filings_enabled,
        market_sentiment_enabled=(resolved_settings.digital_oracle_market_sentiment_enabled),
        prediction_markets_default_item_limit=(
            resolved_settings.digital_oracle_prediction_markets_default_item_limit
        ),
        sec_filings_default_item_limit=(
            resolved_settings.digital_oracle_sec_filings_default_item_limit
        ),
        provider_timeout_seconds=resolved_settings.quote_provider_timeout_seconds,
        edgar_contact_email=resolved_settings.digital_oracle_edgar_contact_email,
    )


__all__ = [
    "DIGITAL_ORACLE_PHASE1_PROVIDER_BOUNDARY",
    "DIGITAL_ORACLE_PHASE1_REQUIRES_VENDORED_PACKAGE",
    "DIGITAL_ORACLE_PHASE1_REQUIRES_YFINANCE",
    "EDGAR_CONTACT_EMAIL_MISSING_CODE",
    "EDGAR_CONTACT_EMAIL_MISSING_MESSAGE",
    "EDGAR_CONTACT_EMAIL_SETTING",
    "MARKET_SENTIMENT_PROVIDER_KEY",
    "MARKET_SENTIMENT_SOURCE_URL",
    "PREDICTION_MARKET_VENUES",
    "DigitalOracleProviderConfig",
    "MarketSentimentIndicator",
    "PredictionMarketVenue",
    "get_digital_oracle_provider_config",
]
