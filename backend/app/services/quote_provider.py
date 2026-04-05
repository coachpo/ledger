from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol, cast

import httpx

from app.core.formatting import normalize_currency, normalize_symbol


class QuoteProviderError(Exception):
    pass


@dataclass(slots=True)
class ProviderQuote:
    symbol: str
    price: Decimal
    previous_close: Decimal | None
    currency: str
    provider: str
    as_of: datetime | None
    name: str | None = None


@dataclass(slots=True)
class ProviderHistoryPoint:
    at: datetime
    close: Decimal


@dataclass(slots=True)
class ProviderHistorySeries:
    symbol: str
    currency: str | None
    provider: str
    points: list[ProviderHistoryPoint]


class QuoteProvider(Protocol):
    def fetch_symbol_name(self, symbol: str) -> str | None: ...

    def fetch_quote(self, symbol: str) -> ProviderQuote: ...

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries: ...


class YahooFinanceQuoteProvider:
    provider_name = "yahoo_finance"

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def fetch_symbol_name(self, symbol: str) -> str | None:
        meta = self._fetch_chart_meta(symbol, interval="1d", range_value="1d")
        return _coerce_name(meta.get("longName")) or _coerce_name(meta.get("shortName"))

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        meta = self._fetch_chart_meta(symbol, interval="1d", range_value="1d")
        price = meta.get("regularMarketPrice") or meta.get("previousClose")
        previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
        currency = meta.get("currency")
        name = _coerce_name(meta.get("longName")) or _coerce_name(meta.get("shortName"))
        if price is None or currency is None:
            raise QuoteProviderError(f"Quote payload was incomplete for {symbol}")

        market_time = _coerce_timestamp(meta.get("regularMarketTime"))
        as_of = datetime.fromtimestamp(market_time, tz=UTC) if market_time is not None else None

        return ProviderQuote(
            symbol=normalize_symbol(symbol),
            name=name,
            price=Decimal(str(price)),
            previous_close=(Decimal(str(previous_close)) if previous_close is not None else None),
            currency=normalize_currency(str(currency)),
            provider=self.provider_name,
            as_of=as_of,
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        result = self._fetch_chart_result(symbol, interval=interval, range_value=range_value)
        meta = _as_object_dict(
            result.get("meta", {}), context=f"Historical quote meta for {symbol}"
        )
        indicators = _as_object_dict(
            result.get("indicators", {}),
            context=f"Historical quote indicators for {symbol}",
        )
        indicator_items = _as_object_list(
            indicators.get("quote", []),
            context=f"Historical quote indicator items for {symbol}",
        )
        quote_items = (
            _as_object_dict(indicator_items[0], context=f"Historical quote items for {symbol}")
            if indicator_items
            else {}
        )
        closes = _as_object_list(
            quote_items.get("close", []),
            context=f"Historical close series for {symbol}",
        )
        timestamps = _as_object_list(
            result.get("timestamp", []),
            context=f"Historical timestamps for {symbol}",
        )
        currency = meta.get("currency")

        points: list[ProviderHistoryPoint] = []
        for timestamp_value, close in zip(timestamps, closes, strict=False):
            timestamp = _coerce_timestamp(timestamp_value)
            if timestamp is None or close is None:
                continue

            points.append(
                ProviderHistoryPoint(
                    at=datetime.fromtimestamp(timestamp, tz=UTC),
                    close=Decimal(str(close)),
                )
            )

        if not points:
            raise QuoteProviderError(f"Historical quote payload was empty for {symbol}")

        return ProviderHistorySeries(
            symbol=normalize_symbol(symbol),
            currency=(normalize_currency(str(currency)) if currency is not None else None),
            provider=self.provider_name,
            points=points,
        )

    def _fetch_chart_meta(
        self, symbol: str, *, interval: str, range_value: str
    ) -> dict[str, object]:
        result = self._fetch_chart_result(symbol, interval=interval, range_value=range_value)
        return _as_object_dict(
            result.get("meta", {}),
            context=f"Quote metadata for {symbol}",
        )

    def _fetch_chart_result(
        self, symbol: str, *, interval: str, range_value: str
    ) -> dict[str, object]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {"interval": interval, "range": range_value}
        headers = {"User-Agent": "ledger-backend/0.1"}

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, params=params, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise QuoteProviderError(f"Quote request failed for {symbol}") from exc

        payload = _as_object_dict(response.json(), context=f"Quote payload for {symbol}")
        chart = _as_object_dict(payload.get("chart", {}), context=f"Quote payload for {symbol}")
        result_items = _as_object_list(
            chart.get("result", []),
            context=f"Quote result list for {symbol}",
        )
        if not result_items:
            raise QuoteProviderError(f"Quote payload was empty for {symbol}")

        return _as_object_dict(result_items[0], context=f"Quote result item for {symbol}")


class DeterministicQuoteProvider:
    provider_name = "deterministic_test"

    def __init__(self, *, anchor_date: date | None = None) -> None:
        self.anchor_date = anchor_date or date(2024, 1, 1)

    def fetch_symbol_name(self, symbol: str) -> str | None:
        names = {
            "AAPL": "Apple Inc.",
            "^GSPC": "S&P 500",
            "^IXIC": "NASDAQ Composite",
            "^DJI": "Dow Jones Industrial Average",
        }
        return names.get(normalize_symbol(symbol), normalize_symbol(symbol))

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        current_date = date(2024, 3, 29)
        close = self._price_for_day(symbol, current_date) + Decimal("0.5")
        return ProviderQuote(
            symbol=normalize_symbol(symbol),
            price=close,
            previous_close=close - Decimal("0.5"),
            currency="USD",
            provider=self.provider_name,
            as_of=datetime.combine(current_date, datetime.min.time(), tzinfo=UTC),
            name=self.fetch_symbol_name(symbol),
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        _ = (range_value, interval)
        points = [
            ProviderHistoryPoint(
                at=datetime.combine(point_date, datetime.min.time(), tzinfo=UTC),
                close=self._price_for_day(symbol, point_date) + Decimal("0.5"),
            )
            for point_date in self._iter_days(date(2024, 1, 2), date(2024, 3, 29))
        ]
        return ProviderHistorySeries(
            symbol=normalize_symbol(symbol),
            currency="USD",
            provider=self.provider_name,
            points=points,
        )

    def download_history(self, symbol: str, start: date, end: date) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for point_date in self._iter_days(start, end):
            open_price = self._price_for_day(symbol, point_date)
            rows.append(
                {
                    "date": point_date.isoformat(),
                    "open": float(open_price),
                    "high": float(open_price + Decimal("1.0")),
                    "low": float(open_price - Decimal("1.0")),
                    "close": float(open_price + Decimal("0.5")),
                    "volume": 1_000_000 + (point_date - self.anchor_date).days * 100,
                }
            )
        return rows

    def _iter_days(self, start: date, end: date) -> list[date]:
        current = start
        days: list[date] = []
        while current <= end:
            days.append(current)
            current += timedelta(days=1)
        return days

    def _price_for_day(self, symbol: str, point_date: date) -> Decimal:
        base_prices = {
            "AAPL": Decimal("180.0"),
            "^GSPC": Decimal("4700.0"),
            "^IXIC": Decimal("16000.0"),
            "^DJI": Decimal("38000.0"),
        }
        base = base_prices.get(normalize_symbol(symbol), Decimal("100.0"))
        offset = Decimal((point_date - self.anchor_date).days) / Decimal("10")
        return base + offset


def _as_object_dict(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QuoteProviderError(f"{context} was malformed")

    return cast(dict[str, object], value)


def _as_object_list(value: object, *, context: str) -> list[object]:
    if not isinstance(value, list):
        raise QuoteProviderError(f"{context} was malformed")

    return cast(list[object], value)


def _coerce_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None

    name = value.strip()
    return name or None


def _coerce_timestamp(value: object) -> int | None:
    if isinstance(value, int | float):
        return int(value)

    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None

    return None
