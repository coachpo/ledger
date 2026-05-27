from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.core.config import Settings

from .config import (
    EDGAR_CONTACT_EMAIL_MISSING_CODE,
    EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
    EDGAR_CONTACT_EMAIL_SETTING,
    MARKET_SENTIMENT_PROVIDER_KEY,
    MARKET_SENTIMENT_SOURCE_URL,
    PREDICTION_MARKET_VENUES,
    DigitalOracleProviderConfig,
    MarketSentimentIndicator,
    PredictionMarketVenue,
    get_digital_oracle_provider_config,
)

_DIGITAL_ORACLE_PROVIDER_DISABLED_CODE = "digital_oracle_provider_disabled"

_PROVIDER_LABELS: Mapping[str, str] = {
    "polymarket": "Polymarket",
    "kalshi": "Kalshi",
    "edgar": "SEC EDGAR",
    "fear_greed": "Fear & Greed Index",
    "prediction_markets": "Digital Oracle prediction markets",
    "market_sentiment": "Digital Oracle market sentiment",
}


def _empty_failure_details() -> dict[str, object]:
    return {}


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderFailure:
    code: str
    message: str
    details: Mapping[str, object] = field(default_factory=_empty_failure_details)


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderConstructionResult[T]:
    provider: T | None = None
    failure: DigitalOracleProviderFailure | None = None

    @property
    def configured(self) -> bool:
        return self.provider is not None and self.failure is None


@dataclass(frozen=True, slots=True)
class DigitalOracleProviderDescriptor:
    key: str
    label: str
    timeout_seconds: float
    default_item_limit: int | None = None


@dataclass(frozen=True, slots=True)
class PredictionMarketsProviderBundle:
    venues: tuple[PredictionMarketVenue, ...]
    providers: tuple[DigitalOracleProviderDescriptor, ...]
    default_item_limit: int


@dataclass(frozen=True, slots=True)
class SecFilingsProviderBundle:
    provider: DigitalOracleProviderDescriptor
    edgar_contact_email: str
    default_item_limit: int


@dataclass(frozen=True, slots=True)
class MarketSentimentProviderBundle:
    provider: DigitalOracleProviderDescriptor
    indicator: MarketSentimentIndicator
    source_url: str


@dataclass(frozen=True, slots=True)
class DigitalOraclePhase1ProviderBundle:
    prediction_markets: DigitalOracleProviderConstructionResult[PredictionMarketsProviderBundle]
    sec_filings: DigitalOracleProviderConstructionResult[SecFilingsProviderBundle]
    market_sentiment: DigitalOracleProviderConstructionResult[MarketSentimentProviderBundle]


def _configured[T](provider: T) -> DigitalOracleProviderConstructionResult[T]:
    return DigitalOracleProviderConstructionResult(provider=provider)


def _disabled_failure(provider: str) -> DigitalOracleProviderFailure:
    label = _PROVIDER_LABELS[provider]
    return DigitalOracleProviderFailure(
        code=_DIGITAL_ORACLE_PROVIDER_DISABLED_CODE,
        message=f"{label} provider is disabled by backend configuration.",
        details={"provider": provider},
    )


def _descriptor(
    *,
    key: str,
    config: DigitalOracleProviderConfig,
    default_item_limit: int | None = None,
) -> DigitalOracleProviderDescriptor:
    return DigitalOracleProviderDescriptor(
        key=key,
        label=_PROVIDER_LABELS[key],
        timeout_seconds=config.provider_timeout_seconds,
        default_item_limit=default_item_limit,
    )


def _create_prediction_markets_provider_bundle(
    config: DigitalOracleProviderConfig,
) -> DigitalOracleProviderConstructionResult[PredictionMarketsProviderBundle]:
    if not config.prediction_markets_enabled:
        return DigitalOracleProviderConstructionResult[PredictionMarketsProviderBundle](
            failure=_disabled_failure("prediction_markets")
        )

    providers = tuple(
        _descriptor(
            key=venue,
            config=config,
            default_item_limit=config.prediction_markets_default_item_limit,
        )
        for venue in PREDICTION_MARKET_VENUES
    )
    return _configured(
        PredictionMarketsProviderBundle(
            venues=PREDICTION_MARKET_VENUES,
            providers=providers,
            default_item_limit=config.prediction_markets_default_item_limit,
        )
    )


def _create_sec_filings_provider(
    config: DigitalOracleProviderConfig,
) -> DigitalOracleProviderConstructionResult[SecFilingsProviderBundle]:
    if not config.sec_filings_enabled:
        return DigitalOracleProviderConstructionResult[SecFilingsProviderBundle](
            failure=_disabled_failure("edgar")
        )
    if config.edgar_contact_email is None:
        return DigitalOracleProviderConstructionResult[SecFilingsProviderBundle](
            failure=DigitalOracleProviderFailure(
                code=EDGAR_CONTACT_EMAIL_MISSING_CODE,
                message=EDGAR_CONTACT_EMAIL_MISSING_MESSAGE,
                details={
                    "provider": "edgar",
                    "setting": EDGAR_CONTACT_EMAIL_SETTING,
                },
            )
        )

    return _configured(
        SecFilingsProviderBundle(
            provider=_descriptor(
                key="edgar",
                config=config,
                default_item_limit=config.sec_filings_default_item_limit,
            ),
            edgar_contact_email=config.edgar_contact_email,
            default_item_limit=config.sec_filings_default_item_limit,
        )
    )


def _create_market_sentiment_provider(
    config: DigitalOracleProviderConfig,
) -> DigitalOracleProviderConstructionResult[MarketSentimentProviderBundle]:
    if not config.market_sentiment_enabled:
        return DigitalOracleProviderConstructionResult[MarketSentimentProviderBundle](
            failure=_disabled_failure("market_sentiment")
        )

    return _configured(
        MarketSentimentProviderBundle(
            provider=_descriptor(key=MARKET_SENTIMENT_PROVIDER_KEY, config=config),
            indicator=MARKET_SENTIMENT_PROVIDER_KEY,
            source_url=MARKET_SENTIMENT_SOURCE_URL,
        )
    )


def create_prediction_markets_provider_bundle(
    settings: Settings | None = None,
) -> DigitalOracleProviderConstructionResult[PredictionMarketsProviderBundle]:
    config = get_digital_oracle_provider_config(settings)
    return _create_prediction_markets_provider_bundle(config)


def create_sec_filings_provider(
    settings: Settings | None = None,
) -> DigitalOracleProviderConstructionResult[SecFilingsProviderBundle]:
    config = get_digital_oracle_provider_config(settings)
    return _create_sec_filings_provider(config)


def create_market_sentiment_provider(
    settings: Settings | None = None,
) -> DigitalOracleProviderConstructionResult[MarketSentimentProviderBundle]:
    config = get_digital_oracle_provider_config(settings)
    return _create_market_sentiment_provider(config)


def create_digital_oracle_phase1_provider_bundle(
    settings: Settings | None = None,
) -> DigitalOraclePhase1ProviderBundle:
    config = get_digital_oracle_provider_config(settings)
    return DigitalOraclePhase1ProviderBundle(
        prediction_markets=_create_prediction_markets_provider_bundle(config),
        sec_filings=_create_sec_filings_provider(config),
        market_sentiment=_create_market_sentiment_provider(config),
    )


__all__ = [
    "DigitalOraclePhase1ProviderBundle",
    "DigitalOracleProviderConstructionResult",
    "DigitalOracleProviderDescriptor",
    "DigitalOracleProviderFailure",
    "MarketSentimentProviderBundle",
    "PredictionMarketsProviderBundle",
    "SecFilingsProviderBundle",
    "create_digital_oracle_phase1_provider_bundle",
    "create_market_sentiment_provider",
    "create_prediction_markets_provider_bundle",
    "create_sec_filings_provider",
]
