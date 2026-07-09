from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import cast

from app.agents.runtime_tools.types import RuntimeToolWarning
from app.extensions.signaldeck_digital_oracle.config import (
    CryptoDerivativesVenue,
    MacroRatesSource,
    PredictionMarketVenue,
)
from app.extensions.signaldeck_digital_oracle.types import (
    DigitalOracleCftcPositioningProviderQuery,
    DigitalOracleCftcPositioningProviderResult,
    DigitalOracleCryptoDerivativesProviderQuery,
    DigitalOracleCryptoDerivativesProviderResult,
    DigitalOracleMacroRatesProviderQuery,
    DigitalOracleMacroRatesProviderResult,
    DigitalOracleMacroRatesSeries,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentProviderResult,
    DigitalOracleOptionsProviderQuery,
    DigitalOracleOptionsProviderResult,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsProviderResult,
    DigitalOracleSecOwnershipTransaction,
    DigitalOracleSecSearchHit,
)
from app.services.news_provider import ProviderNewsItem, ProviderNewsResult
from app.services.quote_provider import (
    ProviderFinancialStatement,
    ProviderFinancialStatementLine,
    ProviderFundamentalMetric,
    ProviderFundamentals,
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderInsiderTransaction,
    ProviderOhlcvRow,
    ProviderOhlcvSeries,
    ProviderQuote,
    QuoteProviderError,
)

FAKE_PROVIDER_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


class FakeDigitalOracleProvider:
    def __init__(
        self,
        provider: str | DigitalOracleMarketSentimentProviderResult = "fake",
        *,
        events: Sequence[DigitalOraclePredictionMarketEvent] = (),
        warnings: Sequence[RuntimeToolWarning] = (),
        result: object | None = None,
        series: Sequence[DigitalOracleMacroRatesSeries] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        if isinstance(provider, DigitalOracleMarketSentimentProviderResult):
            result = provider
            provider = provider.provider
        if provider == "fake" and isinstance(
            result,
            (
                DigitalOracleCftcPositioningProviderResult,
                DigitalOracleCryptoDerivativesProviderResult,
                DigitalOracleMacroRatesProviderResult,
                DigitalOracleMarketSentimentProviderResult,
                DigitalOracleOptionsProviderResult,
                DigitalOraclePredictionMarketsProviderResult,
            ),
        ):
            provider = result.provider
        if provider == "fake" and failure is not None:
            provider = cast(str, failure.details.get("provider", provider))
        self.provider_name = provider
        self.source = cast(MacroRatesSource, provider)
        self.venue = cast(PredictionMarketVenue | CryptoDerivativesVenue, provider)
        self.events = tuple(events)
        self.warnings = tuple(warnings)
        self.result = result
        self.series = tuple(series)
        self.failure = failure
        self.calls: list[object] = []

    def _record_or_fail(self, query: object) -> None:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsProviderQuery,
    ) -> DigitalOraclePredictionMarketsProviderResult:
        self._record_or_fail(query)
        return DigitalOraclePredictionMarketsProviderResult(
            provider=cast(PredictionMarketVenue, self.provider_name),
            events=self.events,
            warnings=self.warnings,
        )

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentProviderQuery,
    ) -> DigitalOracleMarketSentimentProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleMarketSentimentProviderResult, self.result)
        return DigitalOracleMarketSentimentProviderResult(provider=self.provider_name)

    def lookup_macro_rates(
        self,
        query: DigitalOracleMacroRatesProviderQuery,
    ) -> DigitalOracleMacroRatesProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleMacroRatesProviderResult, self.result)
        return DigitalOracleMacroRatesProviderResult(
            provider=cast(MacroRatesSource, self.provider_name),
            series=self.series,
        )

    def lookup_crypto_derivatives(
        self,
        query: DigitalOracleCryptoDerivativesProviderQuery,
    ) -> DigitalOracleCryptoDerivativesProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleCryptoDerivativesProviderResult, self.result)
        return DigitalOracleCryptoDerivativesProviderResult(
            provider=cast(CryptoDerivativesVenue, self.provider_name)
        )

    def lookup_cftc_positioning(
        self,
        query: DigitalOracleCftcPositioningProviderQuery,
    ) -> DigitalOracleCftcPositioningProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleCftcPositioningProviderResult, self.result)
        return DigitalOracleCftcPositioningProviderResult(provider=self.provider_name)

    def lookup_options(
        self,
        query: DigitalOracleOptionsProviderQuery,
    ) -> DigitalOracleOptionsProviderResult:
        self._record_or_fail(query)
        if self.result is not None:
            return cast(DigitalOracleOptionsProviderResult, self.result)
        return DigitalOracleOptionsProviderResult(provider=self.provider_name)


class FakeDigitalOracleSecFilingsProvider:
    provider_name = "edgar"

    def __init__(
        self,
        filings: Sequence[DigitalOracleSecFiling],
        *,
        ownership_transactions: Sequence[DigitalOracleSecOwnershipTransaction] = (),
        search_hits: Sequence[DigitalOracleSecSearchHit] = (),
        failure: DigitalOracleProviderError | None = None,
    ) -> None:
        self.filings = tuple(filings)
        self.ownership_transactions = tuple(ownership_transactions)
        self.search_hits = tuple(search_hits)
        self.failure = failure
        self.calls: list[DigitalOracleSecFilingsProviderQuery] = []

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult:
        self.calls.append(query)
        if self.failure is not None:
            raise self.failure
        return DigitalOracleSecFilingsProviderResult(
            provider=self.provider_name,
            ticker=query.ticker,
            cik="0001045810",
            entity_name="NVIDIA CORP",
            filings=self.filings,
            search_hits=self.search_hits,
            ownership_transactions=self.ownership_transactions,
        )


class FakeJsonClient:
    def __init__(
        self,
        payloads_by_url_fragment: Mapping[str, object] | None = None,
        *,
        payload: object | None = None,
        text_by_url_fragment: Mapping[str, str] | None = None,
    ) -> None:
        self.payloads_by_url_fragment = dict(payloads_by_url_fragment or {})
        self.payload = payload
        self.text_by_url_fragment = dict(text_by_url_fragment or {})
        self.calls: list[dict[str, object]] = []
        self.text_calls: list[dict[str, object]] = []

    def get_json(self, url: str, *, timeout: float, **kwargs: object) -> object:
        call: dict[str, object] = {"url": url, "timeout": timeout}
        params = kwargs.pop("params", None)
        if params is not None:
            call["params"] = dict(cast(Mapping[str, object], params))
        call.update(_recorded_kwargs(kwargs))
        self.calls.append(call)

        if self.payload is not None:
            if isinstance(self.payload, DigitalOracleProviderError):
                raise self.payload
            return self.payload

        for fragment, payload in sorted(
            self.payloads_by_url_fragment.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            if fragment in url:
                if isinstance(payload, DigitalOracleProviderError):
                    raise payload
                return payload
        raise AssertionError(f"No fake JSON payload configured for {url}")

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        self.text_calls.append({"url": url, "timeout": timeout, "contactEmail": contact_email})
        for fragment, payload in self.text_by_url_fragment.items():
            if fragment in url:
                return payload
        raise AssertionError(f"No fake text payload configured for {url}")


def _recorded_kwargs(kwargs: Mapping[str, object]) -> dict[str, object]:
    mapped: dict[str, object] = {}
    for key, value in kwargs.items():
        if value is None:
            continue
        mapped[
            {
                "api_key": "apiKey",
                "contact_email": "contactEmail",
                "report_type": "reportType",
                "source_url": "sourceUrl",
            }.get(key, key)
        ] = value
    return mapped


class FakeOptionsTable:
    def __init__(self, rows: Sequence[Mapping[str, object]]) -> None:
        self.rows = tuple(rows)

    def to_dict(self, orient: str) -> list[Mapping[str, object]]:
        assert orient == "records"
        return list(self.rows)


class FakeOptionsChainPayload:
    def __init__(
        self,
        *,
        calls: Sequence[Mapping[str, object]],
        puts: Sequence[Mapping[str, object]],
    ) -> None:
        self.calls = FakeOptionsTable(calls)
        self.puts = FakeOptionsTable(puts)


class FakeOptionsTicker:
    def __init__(
        self,
        *,
        chains_by_expiration: Mapping[str, FakeOptionsChainPayload],
        spot_price: Decimal | None = Decimal("200"),
    ) -> None:
        self._chains_by_expiration = dict(chains_by_expiration)
        self._spot_price = spot_price
        self.option_chain_calls: list[str] = []

    @property
    def options(self) -> Sequence[str]:
        return tuple(self._chains_by_expiration)

    @property
    def fast_info(self) -> Mapping[str, object]:
        if self._spot_price is None:
            return {}
        return {"last_price": str(self._spot_price)}

    @property
    def info(self) -> Mapping[str, object]:
        return {}

    def option_chain(self, date: str) -> FakeOptionsChainPayload:
        self.option_chain_calls.append(date)
        return self._chains_by_expiration[date]


class FakeOptionsTickerFactory:
    def __init__(self, ticker: FakeOptionsTicker) -> None:
        self.ticker = ticker
        self.symbols: list[str] = []

    def __call__(self, symbol: str) -> FakeOptionsTicker:
        self.symbols.append(symbol)
        return self.ticker


_DIGITAL_ORACLE_FIXTURE_DIR = Path(__file__).resolve().parent / "digital_oracle"


def _normalize_digital_oracle_fixture_params(
    params: Mapping[str, object] | None,
) -> dict[str, object]:
    if params is None:
        return {}
    return {str(key): value for key, value in sorted(params.items()) if value is not None}


def _digital_oracle_fixture_request_key(
    *,
    kind: str,
    url: str,
    params: Mapping[str, object] | None,
) -> str:
    return json.dumps(
        {
            "kind": kind,
            "url": url,
            "params": _normalize_digital_oracle_fixture_params(params),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class DigitalOracleFixtureReplayJsonClient:
    def __init__(
        self,
        fixture_names: Sequence[str],
        *,
        fixture_dir: Path = _DIGITAL_ORACLE_FIXTURE_DIR,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._fixtures: dict[str, dict[str, object]] = {}
        for fixture_name in fixture_names:
            path = fixture_dir / fixture_name
            if not path.exists():
                raise AssertionError(f"Missing Digital Oracle fixture file: {path}")
            try:
                raw_payload = cast(object, json.loads(path.read_text()))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"Malformed Digital Oracle fixture JSON: {path}") from exc
            if not isinstance(raw_payload, dict):
                raise AssertionError(f"Digital Oracle fixture must be an object: {path}")
            fixture = cast(dict[str, object], raw_payload)
            kind = fixture.get("kind")
            request = fixture.get("request")
            if kind != "json" or not isinstance(request, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid envelope: {path}")
            request_payload = cast(dict[str, object], request)
            url = request_payload.get("url")
            params = request_payload.get("params")
            if not isinstance(url, str) or not isinstance(params, dict):
                raise AssertionError(f"Digital Oracle fixture has invalid request: {path}")
            has_response = "response" in fixture
            has_error = "error" in fixture
            if has_response == has_error:
                raise AssertionError(
                    f"Digital Oracle fixture must contain exactly one response or error: {path}"
                )
            params_payload = cast(dict[str, object], params)
            key = _digital_oracle_fixture_request_key(
                kind="json",
                url=url,
                params=params_payload,
            )
            if key in self._fixtures:
                raise AssertionError(f"Duplicate Digital Oracle fixture request: {path}")
            self._fixtures[key] = fixture

    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        params: Mapping[str, object] | None = None,
        provider: PredictionMarketVenue | str | None = None,
        contact_email: str | None = None,
        source_url: str | None = None,
    ) -> object:
        normalized_params = _normalize_digital_oracle_fixture_params(params)
        call: dict[str, object] = {"url": url, "timeout": timeout, "params": normalized_params}
        if provider is not None:
            call["provider"] = provider
        if contact_email is not None:
            call["contactEmail"] = contact_email
        if source_url is not None:
            call["sourceUrl"] = source_url
        self.calls.append(call)
        key = _digital_oracle_fixture_request_key(kind="json", url=url, params=normalized_params)
        fixture = self._fixtures.get(key)
        if fixture is None:
            raise AssertionError(
                f"Missing Digital Oracle fixture for {url} params={normalized_params}"
            )
        error = fixture.get("error")
        if isinstance(error, dict):
            error_payload = cast(dict[str, object], error)
            message = error_payload.get("message")
            code = error_payload.get("code")
            details = error_payload.get("details")
            raise DigitalOracleProviderError(
                message if isinstance(message, str) else "Digital Oracle fixture provider error",
                code=code if isinstance(code, str) else "provider_error",
                details=cast(Mapping[str, object], details if isinstance(details, dict) else {}),
            )
        return fixture["response"]

    def get_text(self, url: str, *, timeout: float, contact_email: str) -> str:
        del timeout, contact_email
        raise AssertionError(f"No Digital Oracle text fixture configured for {url}")


class FakeFinanceProvider:
    def __init__(
        self,
        *,
        provider_name: str = "fake_runtime_provider",
        failing_symbols: set[str] | None = None,
        failure: QuoteProviderError | None = None,
        empty: bool = False,
        news_count: int = 0,
        insider_count: int = 0,
    ) -> None:
        self.provider_name = provider_name
        self.failing_symbols = failing_symbols or set()
        self.failure = failure
        self.empty = empty
        self.news_count = news_count
        self.insider_count = insider_count
        self.quote_calls: list[str] = []
        self.history_calls: list[tuple[str, str, str]] = []
        self.ohlcv_calls: list[tuple[str, datetime, datetime, str]] = []
        self.fundamental_calls: list[str] = []
        self.news_calls: list[
            tuple[list[str], str | None, str, datetime | None, datetime | None, int]
        ] = []
        self.insider_calls: list[tuple[str, datetime | None, datetime | None, int]] = []

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol.upper()} Incorporated"

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        self.quote_calls.append(normalized_symbol)
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"Quote unavailable for {normalized_symbol}")
        price = Decimal("120.25000000") if normalized_symbol == "NVDA" else Decimal("410.50000000")
        return ProviderQuote(
            symbol=normalized_symbol,
            name=f"{normalized_symbol} Incorporated",
            price=price,
            previous_close=price - Decimal("0.50000000"),
            currency="USD",
            provider=self.provider_name,
            as_of=FAKE_PROVIDER_NOW,
        )

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        normalized_symbol = symbol.upper()
        self.history_calls.append((normalized_symbol, range_value, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"History unavailable for {normalized_symbol}")
        return ProviderHistorySeries(
            symbol=normalized_symbol,
            currency="USD",
            provider=self.provider_name,
            points=[
                ProviderHistoryPoint(
                    at=datetime(2026, 1, 1, tzinfo=UTC),
                    close=Decimal("118.75"),
                ),
                ProviderHistoryPoint(
                    at=datetime(2026, 1, 2, tzinfo=UTC),
                    close=Decimal("119.75"),
                ),
                ProviderHistoryPoint(at=FAKE_PROVIDER_NOW, close=Decimal("120.25")),
            ],
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        normalized_symbol = symbol.upper()
        self.ohlcv_calls.append((normalized_symbol, start_date, end_date, interval))
        if normalized_symbol in self.failing_symbols:
            raise QuoteProviderError(f"OHLCV unavailable for {normalized_symbol}")
        mid_session = datetime(2026, 1, 2, 12, 0, tzinfo=timezone(timedelta(hours=-5)))
        return ProviderOhlcvSeries(
            symbol=normalized_symbol,
            currency="USD",
            provider=self.provider_name,
            rows=[
                ProviderOhlcvRow(
                    at=end_date + timedelta(days=1),
                    open=Decimal("999.00"),
                    high=Decimal("1000.00"),
                    low=Decimal("998.00"),
                    close=Decimal("999.50"),
                    volume=9999,
                ),
                ProviderOhlcvRow(
                    at=start_date,
                    open=Decimal("118.00"),
                    high=Decimal("121.00"),
                    low=Decimal("117.00"),
                    close=Decimal("119.75"),
                    volume=1000,
                    adjusted_close=Decimal("119.50"),
                ),
                ProviderOhlcvRow(
                    at=mid_session,
                    open=Decimal("119.00"),
                    high=Decimal("122.00"),
                    low=Decimal("118.00"),
                    close=Decimal("120.00"),
                    volume=1100,
                    adjusted_close=Decimal("119.80"),
                ),
                ProviderOhlcvRow(
                    at=start_date - timedelta(days=1),
                    open=Decimal("1.00"),
                    high=Decimal("2.00"),
                    low=Decimal("0.50"),
                    close=Decimal("1.50"),
                    volume=1,
                ),
                ProviderOhlcvRow(
                    at=end_date,
                    open=Decimal("119.75"),
                    high=Decimal("121.50"),
                    low=Decimal("119.00"),
                    close=Decimal("120.25"),
                    volume=1200,
                ),
            ],
        )

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        normalized_symbol = symbol.upper()
        self.fundamental_calls.append(normalized_symbol)
        if self.failure is not None:
            raise self.failure
        if self.empty:
            return ProviderFundamentals(
                symbol=normalized_symbol,
                provider=self.provider_name,
                as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
                metrics=[],
                statements=[],
            )
        return ProviderFundamentals(
            symbol=normalized_symbol,
            provider=self.provider_name,
            as_of=datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=-5))),
            metrics=[
                ProviderFundamentalMetric(
                    name="market_cap",
                    value=Decimal("1000000.50"),
                    currency="USD",
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="revenue_growth",
                    value=Decimal("0.18"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
                ProviderFundamentalMetric(
                    name="free_cash_flow_margin",
                    value=Decimal("0.19"),
                    period="ttm",
                    as_of=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                ),
            ],
            statements=[
                ProviderFinancialStatement(
                    statement_type="income_statement",
                    period="annual",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="revenue",
                            value=Decimal("500000.25"),
                            currency="USD",
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="balance_sheet",
                    period="quarterly",
                    period_end=datetime(2025, 10, 31, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="assets",
                            value=Decimal("750000.00"),
                            currency="USD",
                        )
                    ],
                ),
                ProviderFinancialStatement(
                    statement_type="cash_flow",
                    period="trailing_twelve_months",
                    period_end=datetime(2026, 1, 1, 21, tzinfo=timezone(timedelta(hours=-5))),
                    lines=[
                        ProviderFinancialStatementLine(
                            name="operating_cash_flow",
                            value=Decimal("125000.75"),
                            currency="USD",
                        )
                    ],
                ),
            ],
        )

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        scope: str,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        self.news_calls.append((symbols, query, scope, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderNewsResult(
            provider=self.provider_name,
            items=[
                ProviderNewsItem(
                    title=f"News {index}",
                    source="wire",
                    published_at=datetime(2026, 1, 2, index, tzinfo=UTC),
                    symbols=symbols,
                    sentiment="neutral",
                )
                for index in range(self.news_count)
            ],
        )

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        normalized_symbol = symbol.upper()
        self.insider_calls.append((normalized_symbol, start_date, end_date, limit))
        if self.failure is not None:
            raise self.failure
        return ProviderInsiderData(
            symbol=normalized_symbol,
            provider=self.provider_name,
            transactions=[
                ProviderInsiderTransaction(
                    insider_name=f"Insider {index}",
                    role="Director",
                    transaction_type="BUY",
                    shares=Decimal("10"),
                    price=Decimal("120.25"),
                    value=Decimal("1202.50"),
                    filed_at=datetime(2026, 1, 3, index, tzinfo=UTC),
                    transaction_date=datetime(2026, 1, 2, index, tzinfo=UTC),
                )
                for index in range(self.insider_count)
            ],
        )
