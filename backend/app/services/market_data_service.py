from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TypeVar

from sqlalchemy.orm import Session

from app.agents import get_default_tool_catalog
from app.agents.runtime_tools.types import RuntimeToolWarning
from app.core.config import Settings, get_settings
from app.core.formatting import normalize_symbol, to_utc, utcnow
from app.models.market_quote import MarketQuote
from app.repositories.market_quote import MarketQuoteRepository
from app.schemas.common import to_camel
from app.schemas.market_data import (
    MarketHistoryPointRead,
    MarketHistoryRead,
    MarketHistorySeriesRead,
    MarketQuoteListRead,
    MarketQuoteRead,
)
from app.services.capability_service import CapabilityService, RuntimeToolGrantPolicy
from app.services.extension_gate import (
    MARKET_DATA_SERVICE_SURFACE,
    require_finance_workspace_enabled,
)
from app.services.market_data_snapshots import (
    MarketDataFinancialStatement as RuntimeFinancialStatement,
)
from app.services.market_data_snapshots import (
    MarketDataFinancialStatementLine as RuntimeFinancialStatementLine,
)
from app.services.market_data_snapshots import (
    MarketDataFundamentalMetric as RuntimeFundamentalMetric,
)
from app.services.market_data_snapshots import (
    MarketDataFundamentalsLookupResult as RuntimeFundamentalsLookupResult,
)
from app.services.market_data_snapshots import (
    MarketDataIndicatorLookupResult as RuntimeIndicatorLookupResult,
)
from app.services.market_data_snapshots import MarketDataIndicatorRow as RuntimeIndicatorRow
from app.services.market_data_snapshots import MarketDataIndicatorValue as RuntimeIndicatorValue
from app.services.market_data_snapshots import (
    MarketDataInsiderDataLookupResult as RuntimeInsiderDataLookupResult,
)
from app.services.market_data_snapshots import (
    MarketDataInsiderTransaction as RuntimeInsiderTransaction,
)
from app.services.market_data_snapshots import MarketDataNewsItem as RuntimeNewsItem
from app.services.market_data_snapshots import MarketDataNewsLookupResult as RuntimeNewsLookupResult
from app.services.market_data_snapshots import (
    MarketDataOhlcvLookupResult as RuntimeOhlcvLookupResult,
)
from app.services.market_data_snapshots import MarketDataOhlcvRow as RuntimeOhlcvRow
from app.services.market_data_snapshots import MarketDataOhlcvSeries as RuntimeOhlcvSeries
from app.services.portfolio_service import PortfolioService
from app.services.quote_provider import (
    ProviderFinancialStatement,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderNewsItem,
    ProviderNewsResult,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProvider,
    QuoteProviderError,
    QuoteProviderRateLimitError,
)

_ProviderResultT = TypeVar("_ProviderResultT")


@dataclass(frozen=True, slots=True)
class MarketClosePoint:
    at: datetime
    close: Decimal


_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(api[_ -]?key|token|secret|password|credential)(\s*[=:]\s*)([^\s,;]+)",
    re.IGNORECASE,
)
_SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9][A-Za-z0-9_-]*")
_SENSITIVE_WARNING_DETAIL_KEY_RE = re.compile(
    r"api[_-]?key|authorization|bearer|credential|password|secret|token",
    re.IGNORECASE,
)
_WARNING_DETAIL_KEY_TOKEN_RE = re.compile(r"[^A-Za-z0-9]+")

__all__ = [
    "MarketClosePoint",
    "MarketDataService",
    "ProviderFinancialStatement",
    "ProviderFundamentalMetric",
    "ProviderFundamentals",
    "ProviderHistoryPoint",
    "ProviderHistorySeries",
    "ProviderInsiderData",
    "ProviderInsiderTransaction",
    "ProviderNewsItem",
    "ProviderNewsResult",
    "ProviderOhlcvRow",
    "ProviderOhlcvSeries",
    "ProviderQuote",
    "QuoteProvider",
    "QuoteProviderError",
    "QuoteProviderRateLimitError",
]


class MarketDataService:
    history_interval_by_range: dict[str, str] = {
        "1mo": "1d",
        "3mo": "1d",
        "ytd": "1wk",
        "1y": "1wk",
        "max": "1mo",
    }
    ohlcv_interval: str = "1d"
    ohlcv_default_row_limit: int = 250
    ohlcv_max_row_limit: int = 500
    indicator_default_sma_windows: tuple[int, ...] = (20,)
    provider_fallback_max_attempts: int = 3
    news_default_item_limit: int = 25
    news_max_item_limit: int = 50
    insider_default_transaction_limit: int = 50
    insider_max_transaction_limit: int = 100

    def __init__(self, session: Session, quote_provider: QuoteProvider) -> None:
        self.session: Session = session
        self.quote_provider: QuoteProvider = quote_provider
        self.portfolio_service: PortfolioService = PortfolioService(session)
        self.repository: MarketQuoteRepository = MarketQuoteRepository(session)
        self.settings: Settings = get_settings()

    def _require_enabled(self) -> None:
        _ = require_finance_workspace_enabled(self.session, surface=MARKET_DATA_SERVICE_SURFACE)

    def get_quotes(self, portfolio_id: int, symbols: list[str]) -> MarketQuoteListRead:
        self._require_enabled()
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
        self._require_enabled()
        _ = self.portfolio_service.get_portfolio_model(portfolio_id)
        return self._build_history_read(symbols, range_value)

    def lookup_quote_snapshot(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
        symbol: str,
        base_currency: str = "USD",
    ) -> tuple[MarketQuoteRead | None, list[str]]:
        self._require_enabled()
        CapabilityService(
            self.session,
            get_default_tool_catalog(),
        ).require_runtime_tool_grant(
            capability_references=capability_references,
            grant_policy=grant_policy,
        )
        return self.get_quote_snapshot(symbol, base_currency=base_currency)

    def lookup_history_snapshot(
        self,
        *,
        capability_references: Sequence[dict[str, object]],
        grant_policy: RuntimeToolGrantPolicy,
        symbol: str,
        range_value: str,
    ) -> MarketHistoryRead:
        self._require_enabled()
        CapabilityService(
            self.session,
            get_default_tool_catalog(),
        ).require_runtime_tool_grant(
            capability_references=capability_references,
            grant_policy=grant_policy,
        )
        return self.get_history_snapshot(symbol, range_value)

    def get_quote_snapshot(
        self, symbol: str, *, base_currency: str = "USD"
    ) -> tuple[MarketQuoteRead | None, list[str]]:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            return None, ["Symbol is required"]
        quote, warning, was_updated = self._resolve_quote(normalized_symbol, base_currency)
        if was_updated:
            self.session.commit()
        return quote, ([warning] if warning is not None else [])

    def get_history_snapshot(self, symbol: str, range_value: str) -> MarketHistoryRead:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")
        return self._build_history_read([normalized_symbol], range_value)

    def get_close_history_snapshot(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MarketClosePoint]:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")

        provider_series = self.quote_provider.fetch_ohlcv(
            normalized_symbol,
            start_date=normalized_start,
            end_date=normalized_end,
            interval=self.ohlcv_interval,
        )
        return self._build_close_history_points(
            provider_series.rows,
            start_date=normalized_start,
            end_date=normalized_end,
        )

    def get_ohlcv_snapshot(
        self,
        symbols: list[str],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int | None = None,
    ) -> RuntimeOhlcvLookupResult:
        self._require_enabled()
        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")

        effective_row_limit = self._normalize_ohlcv_row_limit(row_limit)
        seen_symbols: set[str] = set()
        series: list[RuntimeOhlcvSeries] = []
        warnings: list[RuntimeToolWarning] = []

        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue

            seen_symbols.add(symbol)

            try:
                provider_series = self.quote_provider.fetch_ohlcv(
                    symbol,
                    start_date=normalized_start,
                    end_date=normalized_end,
                    interval=self.ohlcv_interval,
                )
            except QuoteProviderError:
                warnings.append(
                    RuntimeToolWarning(
                        code="ohlcv_unavailable",
                        message=f"No OHLCV data available for {symbol}",
                        details={"symbol": symbol},
                    )
                )
                continue

            rows = self._build_ohlcv_rows(
                provider_series.rows,
                start_date=normalized_start,
                end_date=normalized_end,
                row_limit=effective_row_limit,
            )
            if not rows:
                warnings.append(
                    RuntimeToolWarning(
                        code="ohlcv_unavailable",
                        message=f"No OHLCV data available for {symbol}",
                        details={"symbol": symbol},
                    )
                )
                continue

            series.append(
                RuntimeOhlcvSeries(
                    symbol=normalize_symbol(provider_series.symbol),
                    currency=provider_series.currency,
                    provider=provider_series.provider,
                    rows=rows,
                )
            )

        return RuntimeOhlcvLookupResult(
            start_date=normalized_start,
            end_date=normalized_end,
            series=series,
            warnings=warnings,
        )

    def get_indicator_snapshot(
        self,
        symbol: str,
        *,
        current_date: datetime,
        start_date: datetime,
        end_date: datetime,
        sma_windows: Sequence[int] | None = None,
        row_limit: int | None = None,
    ) -> RuntimeIndicatorLookupResult:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        normalized_current = to_utc(current_date)
        normalized_start = to_utc(start_date)
        normalized_end = to_utc(end_date)
        if normalized_start > normalized_end:
            raise QuoteProviderError("startDate must be before or equal to endDate")
        if normalized_end > normalized_current:
            raise QuoteProviderError("endDate cannot be after currentDate")

        normalized_windows = self._normalize_indicator_sma_windows(sma_windows)
        ohlcv_result = self.get_ohlcv_snapshot(
            [normalized_symbol],
            start_date=normalized_start,
            end_date=normalized_end,
            row_limit=row_limit,
        )
        if not ohlcv_result.series:
            return RuntimeIndicatorLookupResult(
                symbol=normalized_symbol,
                provider=str(getattr(self.quote_provider, "provider_name", "")),
                current_date=normalized_current,
                start_date=normalized_start,
                end_date=normalized_end,
                rows=[],
                warnings=ohlcv_result.warnings,
            )

        ohlcv_series = ohlcv_result.series[0]
        return RuntimeIndicatorLookupResult(
            symbol=ohlcv_series.symbol,
            provider=ohlcv_series.provider,
            current_date=normalized_current,
            start_date=normalized_start,
            end_date=normalized_end,
            rows=self._build_indicator_rows(
                ohlcv_series.rows,
                current_date=normalized_current,
                sma_windows=normalized_windows,
            ),
            warnings=ohlcv_result.warnings,
        )

    def get_fundamentals_snapshot(
        self,
        symbol: str,
        *,
        providers: Sequence[QuoteProvider] | None = None,
    ) -> RuntimeFundamentalsLookupResult:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            operation="fundamentals",
            call=lambda provider: provider.fetch_fundamentals(normalized_symbol),
        )
        if provider_result is None:
            return RuntimeFundamentalsLookupResult(
                symbol=normalized_symbol,
                provider="",
                as_of=utcnow(),
                metrics=[],
                statements=[],
                warnings=warnings,
            )

        metrics = self._build_fundamental_metrics(provider_result.metrics)
        statements = [
            RuntimeFinancialStatement(
                statement_type=statement.statement_type,
                period=statement.period,
                period_end=to_utc(statement.period_end),
                lines=[
                    RuntimeFinancialStatementLine(
                        name=line.name,
                        value=line.value,
                        currency=line.currency,
                    )
                    for line in statement.lines
                ],
            )
            for statement in provider_result.statements
        ]
        if not metrics and not statements:
            warnings.append(
                self._runtime_warning(
                    code="fundamentals_empty",
                    message=f"No fundamentals returned for {normalized_symbol}",
                    details={"symbol": normalized_symbol, "provider": provider_result.provider},
                )
            )
        return RuntimeFundamentalsLookupResult(
            symbol=normalize_symbol(provider_result.symbol),
            provider=provider_result.provider,
            as_of=to_utc(provider_result.as_of),
            metrics=metrics,
            statements=statements,
            warnings=warnings,
        )

    def get_news_snapshot(
        self,
        *,
        symbols: list[str] | None = None,
        query: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        item_limit: int | None = None,
        providers: Sequence[QuoteProvider] | None = None,
    ) -> RuntimeNewsLookupResult:
        self._require_enabled()
        normalized_symbols = self._normalize_optional_symbols(symbols or [])
        normalized_start = to_utc(start_date) if start_date is not None else None
        normalized_end = to_utc(end_date) if end_date is not None else None
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise QuoteProviderError("startDate must be before or equal to endDate")
        effective_limit = self._normalize_result_limit(
            item_limit,
            default_limit=self.news_default_item_limit,
            max_limit=self.news_max_item_limit,
            label="News itemLimit",
        )

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            operation="news",
            call=lambda provider: provider.fetch_news(
                symbols=normalized_symbols,
                query=query.strip() if query is not None else None,
                start_date=normalized_start,
                end_date=normalized_end,
                limit=effective_limit + 1,
            ),
        )
        items = self._build_news_items(provider_result.items if provider_result is not None else [])
        if len(items) > effective_limit:
            items = items[:effective_limit]
            warnings.append(
                self._runtime_warning(
                    code="news_truncated",
                    message=f"News results were truncated to {effective_limit} items",
                    details={"limit": str(effective_limit)},
                )
            )
        if provider_result is not None and not items:
            warnings.append(
                self._runtime_warning(
                    code="news_empty",
                    message="No news returned for the request",
                    details={"symbols": ",".join(normalized_symbols)},
                )
            )
        return RuntimeNewsLookupResult(
            query=query.strip() if query is not None and query.strip() else None,
            symbols=normalized_symbols,
            start_date=normalized_start,
            end_date=normalized_end,
            items=items,
            warnings=warnings,
        )

    def get_insider_transactions_snapshot(
        self,
        symbol: str,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        transaction_limit: int | None = None,
        providers: Sequence[QuoteProvider] | None = None,
    ) -> RuntimeInsiderDataLookupResult:
        self._require_enabled()
        normalized_symbol = normalize_symbol(symbol)
        if not normalized_symbol:
            raise QuoteProviderError("Symbol is required")
        normalized_start = to_utc(start_date) if start_date is not None else None
        normalized_end = to_utc(end_date) if end_date is not None else None
        if (
            normalized_start is not None
            and normalized_end is not None
            and normalized_start > normalized_end
        ):
            raise QuoteProviderError("startDate must be before or equal to endDate")
        effective_limit = self._normalize_result_limit(
            transaction_limit,
            default_limit=self.insider_default_transaction_limit,
            max_limit=self.insider_max_transaction_limit,
            label="Insider transactionLimit",
        )

        provider_result, warnings = self._resolve_with_provider_fallback(
            providers,
            operation="insider",
            call=lambda provider: provider.fetch_insider_transactions(
                normalized_symbol,
                start_date=normalized_start,
                end_date=normalized_end,
                limit=effective_limit + 1,
            ),
        )
        transactions = self._build_insider_transactions(
            provider_result.transactions if provider_result is not None else []
        )
        if len(transactions) > effective_limit:
            transactions = transactions[:effective_limit]
            warnings.append(
                self._runtime_warning(
                    code="insider_truncated",
                    message=f"Insider transactions were truncated to {effective_limit} rows",
                    details={"limit": str(effective_limit), "symbol": normalized_symbol},
                )
            )
        if provider_result is not None and not transactions:
            warnings.append(
                self._runtime_warning(
                    code="insider_empty",
                    message=f"No insider transactions returned for {normalized_symbol}",
                    details={"symbol": normalized_symbol, "provider": provider_result.provider},
                )
            )
        return RuntimeInsiderDataLookupResult(
            symbol=(
                normalize_symbol(provider_result.symbol)
                if provider_result is not None
                else normalized_symbol
            ),
            provider=provider_result.provider if provider_result is not None else "",
            start_date=normalized_start,
            end_date=normalized_end,
            transactions=transactions,
            warnings=warnings,
        )

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

    def _build_close_history_points(
        self,
        rows: list[ProviderOhlcvRow],
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[MarketClosePoint]:
        points: list[MarketClosePoint] = []
        for row in rows:
            row_time = to_utc(row.at)
            if start_date <= row_time <= end_date:
                points.append(MarketClosePoint(at=row_time, close=row.close))

        points.sort(key=lambda point: point.at)
        return points

    def _build_ohlcv_rows(
        self,
        rows: list[ProviderOhlcvRow],
        *,
        start_date: datetime,
        end_date: datetime,
        row_limit: int,
    ) -> list[RuntimeOhlcvRow]:
        normalized_rows: list[tuple[datetime, ProviderOhlcvRow]] = []
        for row in rows:
            row_time = to_utc(row.at)
            if start_date <= row_time <= end_date:
                normalized_rows.append((row_time, row))

        normalized_rows.sort(key=lambda item: item[0])
        selected_rows = normalized_rows[-row_limit:]
        return [
            RuntimeOhlcvRow(
                at=row_time,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                adjusted_close=row.adjusted_close,
            )
            for row_time, row in selected_rows
        ]

    def _build_indicator_rows(
        self,
        rows: list[RuntimeOhlcvRow],
        *,
        current_date: datetime,
        sma_windows: tuple[int, ...],
    ) -> list[RuntimeIndicatorRow]:
        closes = [row.close for row in rows]
        has_enough_history = {window: len(closes) >= window for window in sma_windows}
        indicator_rows: list[RuntimeIndicatorRow] = []
        for row_index, row in enumerate(rows):
            row_time = to_utc(row.at)
            if row_time > current_date:
                raise QuoteProviderError("Indicator OHLCV rows cannot be after currentDate")

            values = [RuntimeIndicatorValue(name="close", value=row.close)]
            for window in sma_windows:
                name = f"sma_{window}"
                available_count = row_index + 1
                if available_count < window:
                    values.append(
                        RuntimeIndicatorValue(
                            name=name,
                            value=None,
                            null_reason=(
                                "warmup" if has_enough_history[window] else "insufficient_history"
                            ),
                        )
                    )
                    continue

                window_closes = closes[available_count - window : available_count]
                values.append(
                    RuntimeIndicatorValue(
                        name=name,
                        value=sum(window_closes, Decimal("0")) / Decimal(window),
                    )
                )

            indicator_rows.append(RuntimeIndicatorRow(at=row_time, values=values))

        return indicator_rows

    def _resolve_with_provider_fallback(
        self,
        providers: Sequence[QuoteProvider] | None,
        *,
        operation: str,
        call: Callable[[QuoteProvider], _ProviderResultT],
    ) -> tuple[_ProviderResultT | None, list[RuntimeToolWarning]]:
        ordered_providers = list(providers or [self.quote_provider])[
            : self.provider_fallback_max_attempts
        ]
        warnings: list[RuntimeToolWarning] = []
        if not ordered_providers:
            warnings.append(
                self._runtime_warning(
                    code=f"{operation}_provider_unavailable",
                    message=f"No {operation} providers are configured",
                    details={"operation": operation},
                )
            )
            return None, warnings

        for provider in ordered_providers:
            provider_name = self._provider_name(provider)
            try:
                return call(provider), warnings
            except QuoteProviderError as exc:
                warnings.append(
                    self._runtime_warning(
                        code=self._provider_warning_code(operation, exc),
                        message=self._public_warning_message(
                            str(exc) or f"{operation} provider failed"
                        ),
                        details={
                            **self._public_warning_details(exc.details),
                            "operation": operation,
                            "provider": provider_name,
                        },
                    )
                )

        warnings.append(
            self._runtime_warning(
                code=f"{operation}_unavailable",
                message=f"No {operation} data available from configured providers",
                details={"operation": operation},
            )
        )
        return None, warnings

    def _build_fundamental_metrics(
        self, metrics: list[ProviderFundamentalMetric]
    ) -> list[RuntimeFundamentalMetric]:
        return [
            RuntimeFundamentalMetric(
                name=metric.name,
                value=metric.value,
                currency=metric.currency,
                period=metric.period,
                as_of=to_utc(metric.as_of) if metric.as_of is not None else None,
            )
            for metric in metrics
        ]

    def _build_news_items(self, items: list[ProviderNewsItem]) -> list[RuntimeNewsItem]:
        sorted_items = sorted(items, key=lambda item: to_utc(item.published_at), reverse=True)
        return [
            RuntimeNewsItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=to_utc(item.published_at),
                summary=item.summary,
                symbols=[normalize_symbol(symbol) for symbol in item.symbols or []],
                sentiment=item.sentiment,
            )
            for item in sorted_items
        ]

    def _build_insider_transactions(
        self, transactions: list[ProviderInsiderTransaction]
    ) -> list[RuntimeInsiderTransaction]:
        sorted_transactions = sorted(
            transactions,
            key=lambda transaction: to_utc(transaction.transaction_date),
            reverse=True,
        )
        return [
            RuntimeInsiderTransaction(
                insider_name=transaction.insider_name,
                role=transaction.role,
                transaction_type=transaction.transaction_type,
                shares=transaction.shares,
                price=transaction.price,
                value=transaction.value,
                filed_at=(
                    to_utc(transaction.filed_at) if transaction.filed_at is not None else None
                ),
                transaction_date=to_utc(transaction.transaction_date),
            )
            for transaction in sorted_transactions
        ]

    def _normalize_optional_symbols(self, symbols: list[str]) -> list[str]:
        normalized_symbols: list[str] = []
        seen_symbols: set[str] = set()
        for raw_symbol in symbols:
            symbol = normalize_symbol(raw_symbol)
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            normalized_symbols.append(symbol)
        return normalized_symbols

    def _normalize_result_limit(
        self,
        limit: int | None,
        *,
        default_limit: int,
        max_limit: int,
        label: str,
    ) -> int:
        if limit is None:
            return default_limit
        if limit < 1:
            raise QuoteProviderError(f"{label} must be at least 1")
        if limit > max_limit:
            raise QuoteProviderError(f"{label} must be at most {max_limit}")
        return limit

    def _provider_warning_code(self, operation: str, exc: QuoteProviderError) -> str:
        if exc.code == "provider_api_key_missing":
            return f"{operation}_api_key_missing"
        if exc.code == "provider_timeout":
            return f"{operation}_provider_timeout"
        if exc.code == "provider_rate_limited":
            return f"{operation}_provider_rate_limited"
        if exc.code == "provider_unavailable":
            return f"{operation}_provider_unavailable"
        return f"{operation}_provider_error"

    def _provider_name(self, provider: QuoteProvider) -> str:
        return str(getattr(provider, "provider_name", provider.__class__.__name__))

    def _runtime_warning(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, str],
    ) -> RuntimeToolWarning:
        return RuntimeToolWarning(
            code=code,
            message=self._public_warning_message(message),
            details=self._public_warning_details(details),
        )

    @staticmethod
    def _public_warning_message(message: str) -> str:
        redacted_assignments = _SECRET_ASSIGNMENT_RE.sub(
            lambda match: f"{match.group(1)}{match.group(2)}<redacted>",
            message,
        )
        return _SECRET_TOKEN_RE.sub("<redacted>", redacted_assignments)

    @classmethod
    def _public_warning_details(cls, details: dict[str, str]) -> dict[str, str]:
        public_details: dict[str, str] = {}
        for key, value in details.items():
            normalized_key = key.strip()
            if not normalized_key or _SENSITIVE_WARNING_DETAIL_KEY_RE.search(normalized_key):
                continue
            key_tokens = _WARNING_DETAIL_KEY_TOKEN_RE.sub("_", normalized_key).strip("_")
            if not key_tokens:
                continue
            public_details[to_camel(key_tokens)] = cls._public_warning_message(value)
        return public_details

    def _normalize_indicator_sma_windows(
        self, sma_windows: Sequence[int] | None
    ) -> tuple[int, ...]:
        if sma_windows is None:
            return self.indicator_default_sma_windows

        normalized_windows: list[int] = []
        seen_windows: set[int] = set()
        for window in sma_windows:
            if window < 1:
                raise QuoteProviderError("Indicator SMA window must be at least 1")
            if window > self.ohlcv_max_row_limit:
                raise QuoteProviderError(
                    f"Indicator SMA window must be at most {self.ohlcv_max_row_limit}"
                )
            if window in seen_windows:
                continue
            seen_windows.add(window)
            normalized_windows.append(window)

        if not normalized_windows:
            raise QuoteProviderError("At least one indicator SMA window is required")
        return tuple(normalized_windows)

    def _normalize_ohlcv_row_limit(self, row_limit: int | None) -> int:
        if row_limit is None:
            return self.ohlcv_default_row_limit
        if row_limit < 1:
            raise QuoteProviderError("OHLCV rowLimit must be at least 1")
        if row_limit > self.ohlcv_max_row_limit:
            raise QuoteProviderError(f"OHLCV rowLimit must be at most {self.ohlcv_max_row_limit}")
        return row_limit

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
            _ = self.repository.add(cached)
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
