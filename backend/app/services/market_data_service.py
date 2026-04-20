from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.formatting import normalize_symbol, to_utc, utcnow
from app.models.market_quote import MarketQuote
from app.repositories.market_quote import MarketQuoteRepository
from app.schemas.market_data import (
    MarketHistoryPointRead,
    MarketHistoryRead,
    MarketHistorySeriesRead,
    MarketQuoteListRead,
    MarketQuoteRead,
)
from app.services.portfolio_service import PortfolioService
from app.services.quote_provider import (
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderQuote,
    QuoteProvider,
    QuoteProviderError,
)

__all__ = [
    "MarketDataService",
    "ProviderHistoryPoint",
    "ProviderHistorySeries",
    "ProviderQuote",
    "QuoteProvider",
    "QuoteProviderError",
]


class MarketDataService:
    history_interval_by_range = {
        "1mo": "1d",
        "3mo": "1d",
        "ytd": "1wk",
        "1y": "1wk",
        "max": "1mo",
    }

    def __init__(self, session: Session, quote_provider: QuoteProvider) -> None:
        self.session = session
        self.quote_provider = quote_provider
        self.portfolio_service = PortfolioService(session)
        self.repository = MarketQuoteRepository(session)
        self.settings = get_settings()

    def get_quotes(self, portfolio_id: int, symbols: list[str]) -> MarketQuoteListRead:
        portfolio = self.portfolio_service.get_portfolio_model(portfolio_id)
        quotes: list[MarketQuoteRead] = []
        warnings: list[str] = []
        updated_cache = False

        seen_symbols: set[str] = set()
        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)

            quote, warning, was_updated = self._resolve_quote(symbol, portfolio.base_currency)
            if quote is not None:
                quotes.append(quote)
            if warning is not None:
                warnings.append(warning)
            updated_cache = updated_cache or was_updated

        if updated_cache:
            self.session.commit()

        return MarketQuoteListRead(quotes=quotes, warnings=warnings)

    def get_history(
        self, portfolio_id: int, symbols: list[str], range_value: str
    ) -> MarketHistoryRead:
        self.portfolio_service.get_portfolio_model(portfolio_id)
        return self._build_history_read(symbols, range_value)

    def get_quote_snapshot(
        self, symbol: str, *, base_currency: str = "USD"
    ) -> tuple[MarketQuoteRead | None, list[str]]:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            return None, ["Symbol is required"]
        quote, warning, was_updated = self._resolve_quote(normalized_symbol, base_currency)
        if was_updated:
            self.session.commit()
        return quote, ([warning] if warning is not None else [])

    def get_history_snapshot(self, symbol: str, range_value: str) -> MarketHistoryRead:
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")
        return self._build_history_read([normalized_symbol], range_value)

    def _build_history_read(self, symbols: list[str], range_value: str) -> MarketHistoryRead:
        interval = self.history_interval_by_range.get(range_value)
        if interval is None:
            raise QuoteProviderError(f"Unsupported history range {range_value}")

        seen_symbols: set[str] = set()
        series: list[MarketHistorySeriesRead] = []
        warnings: list[str] = []

        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue

            seen_symbols.add(symbol)

            try:
                provider_series = self.quote_provider.fetch_history(
                    symbol, range_value=range_value, interval=interval
                )
            except QuoteProviderError:
                warnings.append(f"No history available for {symbol}")
                continue

            series.append(
                MarketHistorySeriesRead(
                    symbol=provider_series.symbol,
                    currency=provider_series.currency,
                    provider=provider_series.provider,
                    points=[
                        MarketHistoryPointRead(at=point.at, close=point.close)
                        for point in provider_series.points
                    ],
                )
            )

        return MarketHistoryRead(
            range=range_value,
            interval=interval,
            series=series,
            warnings=warnings,
        )

    def _resolve_quote(
        self, symbol: str, base_currency: str
    ) -> tuple[MarketQuoteRead | None, str | None, bool]:
        try:
            provider_quote = self.quote_provider.fetch_quote(symbol)
        except QuoteProviderError:
            cached = self.repository.get_latest(symbol)
            if cached is None:
                return None, f"No quote available for {symbol}", False
            if cached.currency != base_currency:
                return None, f"Cached quote currency mismatch for {symbol}", False
            is_stale = self._is_quote_stale(cached.as_of)
            was_updated = cached.is_stale != is_stale
            if was_updated:
                cached.is_stale = is_stale
            return (
                self._to_market_quote_read(cached, previous_close=cached.previous_close),
                f"Using cached quote for {symbol}",
                was_updated,
            )

        if provider_quote.currency != base_currency:
            return None, f"Quote currency mismatch for {symbol}", False

        is_stale = self._is_quote_stale(provider_quote.as_of)
        cached = self.repository.get_by_provider_symbol_as_of(
            provider_quote.provider,
            provider_quote.symbol,
            provider_quote.as_of,
        )
        if cached is None:
            cached = MarketQuote(
                symbol=provider_quote.symbol,
                provider=provider_quote.provider,
                price=provider_quote.price,
                previous_close=provider_quote.previous_close,
                currency=provider_quote.currency,
                name=provider_quote.name,
                as_of=provider_quote.as_of,
                fetched_at=utcnow(),
                is_stale=is_stale,
            )
            self.repository.add(cached)
        else:
            cached.price = provider_quote.price
            cached.previous_close = provider_quote.previous_close
            cached.currency = provider_quote.currency
            cached.name = provider_quote.name
            cached.fetched_at = utcnow()
            cached.is_stale = is_stale

        return (
            self._to_market_quote_read(cached, previous_close=provider_quote.previous_close),
            None,
            True,
        )

    def _is_quote_stale(self, as_of: datetime | None) -> bool:
        if as_of is None:
            return True
        stale_cutoff = utcnow() - timedelta(minutes=self.settings.quote_stale_after_minutes)
        return to_utc(as_of) < stale_cutoff

    def _to_market_quote_read(
        self, quote: MarketQuote, *, previous_close: Decimal | None
    ) -> MarketQuoteRead:
        return MarketQuoteRead(
            symbol=quote.symbol,
            name=quote.name,
            price=quote.price,
            previous_close=previous_close,
            currency=quote.currency,
            provider=quote.provider,
            as_of=quote.as_of,
            is_stale=quote.is_stale,
        )
