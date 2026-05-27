from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import cast

from app.agents.runtime_tools.types import RuntimeToolWarning
from app.core.config import Settings
from app.core.formatting import normalize_symbol

from .config import PREDICTION_MARKET_VENUES, PredictionMarketVenue
from .factory import DigitalOraclePhase1ProviderBundle, create_digital_oracle_phase1_provider_bundle
from .types import (
    DigitalOracleMarketSentimentProvider,
    DigitalOracleMarketSentimentProviderQuery,
    DigitalOracleMarketSentimentQuery,
    DigitalOracleMarketSentimentResult,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketProvider,
    DigitalOraclePredictionMarketsProviderQuery,
    DigitalOraclePredictionMarketsProviderResult,
    DigitalOraclePredictionMarketsQuery,
    DigitalOraclePredictionMarketsResult,
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProvider,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsQuery,
    DigitalOracleSecFilingsResult,
)
from .warnings import (
    empty_result_warning,
    partial_result_warning,
    provider_unavailable_warning,
    truncated_result_warning,
    unavailable_result_warning,
    warning_from_provider_error,
    warning_from_provider_failure,
    warning_from_unhandled_provider_error,
)

_PREDICTION_MARKETS_MAX_ITEM_LIMIT = 20
_SEC_FILINGS_MAX_ITEM_LIMIT = 50
_PREDICTION_MARKETS_OPERATION = "prediction_markets"
_SEC_FILINGS_OPERATION = "sec_filings"
_MARKET_SENTIMENT_OPERATION = "market_sentiment"
_RESOLVED_PREDICTION_MARKET_STATUSES = {"closed", "expired", "resolved", "settled"}


@dataclass(frozen=True, slots=True)
class _ProviderCall[T]:
    provider: str
    call: Callable[[], T]


@dataclass(frozen=True, slots=True)
class _ProviderOutcome[T]:
    provider: str
    result: T | None = None
    warning: RuntimeToolWarning | None = None


class DigitalOraclePhase1Service:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        provider_bundle: DigitalOraclePhase1ProviderBundle | None = None,
        prediction_market_providers: Sequence[DigitalOraclePredictionMarketProvider] = (),
        sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
        market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = None,
    ) -> None:
        self._provider_bundle: DigitalOraclePhase1ProviderBundle = (
            provider_bundle or create_digital_oracle_phase1_provider_bundle(settings)
        )
        self._prediction_market_providers_by_venue: dict[
            PredictionMarketVenue,
            DigitalOraclePredictionMarketProvider,
        ] = {provider.venue: provider for provider in prediction_market_providers}
        self._sec_filings_provider: DigitalOracleSecFilingsProvider | None = sec_filings_provider
        self._market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = (
            market_sentiment_provider
        )

    def lookup_prediction_markets(
        self,
        query: DigitalOraclePredictionMarketsQuery,
    ) -> DigitalOraclePredictionMarketsResult:
        normalized_query = _normalize_text(query.query, field_name="query")
        construction = self._provider_bundle.prediction_markets
        if construction.failure is not None:
            return DigitalOraclePredictionMarketsResult(
                query=normalized_query,
                events=(),
                warnings=(
                    warning_from_provider_failure(
                        construction.failure,
                        operation=_PREDICTION_MARKETS_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction.provider
        if provider_bundle is None:
            return DigitalOraclePredictionMarketsResult(
                query=normalized_query,
                events=(),
                warnings=(unavailable_result_warning(operation=_PREDICTION_MARKETS_OPERATION),),
            )

        venues = _normalize_prediction_venues(query.venues or provider_bundle.venues)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_PREDICTION_MARKETS_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        warnings: list[RuntimeToolWarning] = []
        uncovered_providers: set[str] = set()
        calls: list[_ProviderCall[DigitalOraclePredictionMarketsProviderResult]] = []

        descriptor_by_key = {descriptor.key: descriptor for descriptor in provider_bundle.providers}
        for venue in venues:
            descriptor = descriptor_by_key.get(venue)
            provider = self._prediction_market_providers_by_venue.get(venue)
            if descriptor is None or provider is None:
                warnings.append(
                    provider_unavailable_warning(
                        operation=_PREDICTION_MARKETS_OPERATION,
                        provider=venue,
                    )
                )
                uncovered_providers.add(venue)
                continue
            provider_query = DigitalOraclePredictionMarketsProviderQuery(
                query=normalized_query,
                venue=venue,
                item_limit=item_limit,
                include_resolved=query.include_resolved,
                timeout_seconds=descriptor.timeout_seconds,
            )
            calls.append(
                _ProviderCall(
                    provider=venue,
                    call=lambda provider=provider, provider_query=provider_query: (
                        provider.lookup_prediction_markets(provider_query)
                    ),
                )
            )

        events: list[DigitalOraclePredictionMarketEvent] = []
        for outcome in _gather_provider_calls(calls, operation=_PREDICTION_MARKETS_OPERATION):
            if outcome.warning is not None:
                warnings.append(outcome.warning)
                uncovered_providers.add(outcome.provider)
                continue
            provider_result = cast(DigitalOraclePredictionMarketsProviderResult, outcome.result)
            warnings.extend(provider_result.warnings)
            provider_events = _filter_prediction_market_events(
                provider_result.events,
                include_resolved=query.include_resolved,
            )
            if not provider_events:
                warnings.append(
                    empty_result_warning(
                        operation=_PREDICTION_MARKETS_OPERATION,
                        provider=outcome.provider,
                    )
                )
                uncovered_providers.add(outcome.provider)
                continue
            events.extend(provider_events)

        if len(events) > item_limit:
            events = events[:item_limit]
            warnings.append(
                truncated_result_warning(
                    operation=_PREDICTION_MARKETS_OPERATION,
                    limit=item_limit,
                )
            )
        _append_coverage_warning(
            warnings,
            operation=_PREDICTION_MARKETS_OPERATION,
            requested_providers=venues,
            uncovered_providers=tuple(sorted(uncovered_providers)),
            has_results=bool(events),
        )
        return DigitalOraclePredictionMarketsResult(
            query=normalized_query,
            events=tuple(events),
            warnings=tuple(warnings),
        )

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsQuery,
    ) -> DigitalOracleSecFilingsResult:
        ticker = _normalize_symbol_query(query.ticker, field_name="ticker")
        construction = self._provider_bundle.sec_filings
        if construction.failure is not None:
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                warnings=(
                    warning_from_provider_failure(
                        construction.failure,
                        operation=_SEC_FILINGS_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction.provider
        if provider_bundle is None or self._sec_filings_provider is None:
            return DigitalOracleSecFilingsResult(
                ticker=ticker,
                warnings=(
                    provider_unavailable_warning(
                        operation=_SEC_FILINGS_OPERATION,
                        provider="edgar",
                    ),
                    unavailable_result_warning(operation=_SEC_FILINGS_OPERATION),
                ),
            )

        _validate_date_bounds(query.start_date, query.end_date)
        form_types = _normalize_form_types(query.form_types)
        item_limit = _normalize_limit(
            query.item_limit,
            default_limit=provider_bundle.default_item_limit,
            max_limit=_SEC_FILINGS_MAX_ITEM_LIMIT,
            field_name="itemLimit",
        )
        provider_query = DigitalOracleSecFilingsProviderQuery(
            ticker=ticker,
            form_types=form_types,
            start_date=query.start_date,
            end_date=query.end_date,
            item_limit=item_limit,
            edgar_contact_email=provider_bundle.edgar_contact_email,
            timeout_seconds=provider_bundle.provider.timeout_seconds,
        )
        warnings: list[RuntimeToolWarning] = []
        try:
            provider_result = self._sec_filings_provider.lookup_sec_filings(provider_query)
        except DigitalOracleProviderError as exc:
            warnings.append(
                warning_from_provider_error(
                    exc,
                    operation=_SEC_FILINGS_OPERATION,
                    provider="edgar",
                )
            )
            warnings.append(unavailable_result_warning(operation=_SEC_FILINGS_OPERATION))
            return DigitalOracleSecFilingsResult(ticker=ticker, warnings=tuple(warnings))
        except Exception as exc:
            warnings.append(
                warning_from_unhandled_provider_error(
                    exc,
                    operation=_SEC_FILINGS_OPERATION,
                    provider="edgar",
                )
            )
            warnings.append(unavailable_result_warning(operation=_SEC_FILINGS_OPERATION))
            return DigitalOracleSecFilingsResult(ticker=ticker, warnings=tuple(warnings))

        warnings.extend(provider_result.warnings)
        filtered_filings = _filter_sec_filings(
            provider_result.filings,
            form_types=form_types,
            start_date=query.start_date,
            end_date=query.end_date,
        )
        if len(filtered_filings) > item_limit:
            filtered_filings = filtered_filings[:item_limit]
            warnings.append(
                truncated_result_warning(operation=_SEC_FILINGS_OPERATION, limit=item_limit)
            )
        if not filtered_filings:
            warnings.append(
                empty_result_warning(operation=_SEC_FILINGS_OPERATION, provider="edgar")
            )
        return DigitalOracleSecFilingsResult(
            ticker=ticker,
            cik=provider_result.cik,
            entity_name=provider_result.entity_name,
            filings=tuple(filtered_filings),
            warnings=tuple(warnings),
        )

    def lookup_market_sentiment(
        self,
        query: DigitalOracleMarketSentimentQuery,
    ) -> DigitalOracleMarketSentimentResult:
        construction = self._provider_bundle.market_sentiment
        if construction.failure is not None:
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                warnings=(
                    warning_from_provider_failure(
                        construction.failure,
                        operation=_MARKET_SENTIMENT_OPERATION,
                    ),
                ),
            )
        provider_bundle = construction.provider
        if provider_bundle is None or self._market_sentiment_provider is None:
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url if provider_bundle is not None else None,
                warnings=(
                    provider_unavailable_warning(
                        operation=_MARKET_SENTIMENT_OPERATION,
                        provider="fear_greed",
                    ),
                    unavailable_result_warning(operation=_MARKET_SENTIMENT_OPERATION),
                ),
            )

        provider_query = DigitalOracleMarketSentimentProviderQuery(
            indicator=query.indicator,
            as_of_date=query.as_of_date,
            source_url=provider_bundle.source_url,
            timeout_seconds=provider_bundle.provider.timeout_seconds,
        )
        warnings: list[RuntimeToolWarning] = []
        try:
            provider_result = self._market_sentiment_provider.lookup_market_sentiment(
                provider_query
            )
        except DigitalOracleProviderError as exc:
            warnings.append(
                warning_from_provider_error(
                    exc,
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider="fear_greed",
                )
            )
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url,
                warnings=tuple(warnings),
            )
        except Exception as exc:
            warnings.append(
                warning_from_unhandled_provider_error(
                    exc,
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider="fear_greed",
                )
            )
            return DigitalOracleMarketSentimentResult(
                indicator=query.indicator,
                provider="fear_greed",
                as_of_date=query.as_of_date,
                source_url=provider_bundle.source_url,
                warnings=tuple(warnings),
            )

        warnings.extend(provider_result.warnings)
        if provider_result.score is None and provider_result.label is None:
            warnings.append(
                empty_result_warning(
                    operation=_MARKET_SENTIMENT_OPERATION,
                    provider=provider_result.provider or "fear_greed",
                )
            )
        return DigitalOracleMarketSentimentResult(
            indicator=query.indicator,
            provider=provider_result.provider,
            as_of_date=provider_result.as_of_date or query.as_of_date,
            score=provider_result.score,
            label=provider_result.label,
            previous_close=provider_result.previous_close,
            week_ago=provider_result.week_ago,
            month_ago=provider_result.month_ago,
            year_ago=provider_result.year_ago,
            source_url=provider_result.source_url or provider_bundle.source_url,
            warnings=tuple(warnings),
        )


def create_digital_oracle_phase1_service(
    *,
    settings: Settings | None = None,
    provider_bundle: DigitalOraclePhase1ProviderBundle | None = None,
    prediction_market_providers: Sequence[DigitalOraclePredictionMarketProvider] = (),
    sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
    market_sentiment_provider: DigitalOracleMarketSentimentProvider | None = None,
) -> DigitalOraclePhase1Service:
    return DigitalOraclePhase1Service(
        settings=settings,
        provider_bundle=provider_bundle,
        prediction_market_providers=prediction_market_providers,
        sec_filings_provider=sec_filings_provider,
        market_sentiment_provider=market_sentiment_provider,
    )


def _gather_provider_calls[
    T
](calls: Sequence[_ProviderCall[T]], *, operation: str,) -> tuple[_ProviderOutcome[T], ...]:
    if not calls:
        return ()
    if len(calls) == 1:
        return (_execute_provider_call(calls[0], operation=operation),)

    outcomes_by_index: dict[int, _ProviderOutcome[T]] = {}
    with ThreadPoolExecutor(max_workers=len(calls)) as executor:
        future_by_index = {
            executor.submit(_execute_provider_call, call, operation=operation): index
            for index, call in enumerate(calls)
        }
        for future in as_completed(future_by_index):
            outcomes_by_index[future_by_index[future]] = future.result()
    return tuple(outcomes_by_index[index] for index in sorted(outcomes_by_index))


def _execute_provider_call[
    T
](call: _ProviderCall[T], *, operation: str,) -> _ProviderOutcome[T]:
    try:
        return _ProviderOutcome(provider=call.provider, result=call.call())
    except DigitalOracleProviderError as exc:
        return _ProviderOutcome(
            provider=call.provider,
            warning=warning_from_provider_error(
                exc,
                operation=operation,
                provider=call.provider,
            ),
        )
    except Exception as exc:
        return _ProviderOutcome(
            provider=call.provider,
            warning=warning_from_unhandled_provider_error(
                exc,
                operation=operation,
                provider=call.provider,
            ),
        )


def _normalize_prediction_venues(
    venues: Sequence[PredictionMarketVenue],
) -> tuple[PredictionMarketVenue, ...]:
    normalized: list[PredictionMarketVenue] = []
    seen: set[PredictionMarketVenue] = set()
    for raw_venue in venues:
        venue = cast(PredictionMarketVenue, str(raw_venue).strip().lower())
        if venue in PREDICTION_MARKET_VENUES and venue not in seen:
            normalized.append(venue)
            seen.add(venue)
    if not normalized:
        return PREDICTION_MARKET_VENUES
    return tuple(normalized)


def _filter_prediction_market_events(
    events: Sequence[DigitalOraclePredictionMarketEvent],
    *,
    include_resolved: bool,
) -> tuple[DigitalOraclePredictionMarketEvent, ...]:
    if include_resolved:
        return tuple(events)
    return tuple(
        event
        for event in events
        if event.status.strip().lower() not in _RESOLVED_PREDICTION_MARKET_STATUSES
    )


def _filter_sec_filings(
    filings: Sequence[DigitalOracleSecFiling],
    *,
    form_types: tuple[str, ...],
    start_date: date | None,
    end_date: date | None,
) -> list[DigitalOracleSecFiling]:
    form_type_filter = set(form_types)
    filtered: list[DigitalOracleSecFiling] = []
    for filing in filings:
        if form_type_filter and filing.form_type.strip().upper() not in form_type_filter:
            continue
        if start_date is not None and filing.filing_date < start_date:
            continue
        if end_date is not None and filing.filing_date > end_date:
            continue
        filtered.append(filing)
    return sorted(filtered, key=lambda filing: filing.filing_date, reverse=True)


def _append_coverage_warning(
    warnings: list[RuntimeToolWarning],
    *,
    operation: str,
    requested_providers: tuple[str, ...],
    uncovered_providers: tuple[str, ...],
    has_results: bool,
) -> None:
    if has_results and uncovered_providers:
        warnings.append(
            partial_result_warning(
                operation=operation,
                requested_providers=requested_providers,
                uncovered_providers=uncovered_providers,
            )
        )
    if not has_results:
        warnings.append(unavailable_result_warning(operation=operation))


def _normalize_form_types(form_types: Sequence[str] | None) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_form_type in form_types or ():
        form_type = str(raw_form_type).strip().upper()
        if form_type and form_type not in seen:
            normalized.append(form_type)
            seen.add(form_type)
    return tuple(normalized)


def _normalize_limit(
    value: int | None,
    *,
    default_limit: int,
    max_limit: int,
    field_name: str,
) -> int:
    if value is None:
        return default_limit
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
    if value > max_limit:
        raise ValueError(f"{field_name} must be at most {max_limit}")
    return value


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_symbol_query(value: str, *, field_name: str) -> str:
    normalized = normalize_symbol(value)
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _validate_date_bounds(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("startDate must be before or equal to endDate")


__all__ = [
    "DigitalOraclePhase1Service",
    "create_digital_oracle_phase1_service",
]
