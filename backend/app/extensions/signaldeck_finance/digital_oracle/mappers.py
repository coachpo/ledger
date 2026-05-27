from __future__ import annotations

from app.extensions.signaldeck_finance.runtime_types import (
    RuntimeMarketSentimentLookupResult,
    RuntimePredictionMarketContract,
    RuntimePredictionMarketEvent,
    RuntimePredictionMarketsLookupResult,
    RuntimeSecFiling,
    RuntimeSecFilingsLookupResult,
)

from .types import (
    DigitalOracleMarketSentimentResult,
    DigitalOraclePredictionMarketContract,
    DigitalOraclePredictionMarketEvent,
    DigitalOraclePredictionMarketsResult,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsResult,
)


def map_prediction_markets_result(
    result: DigitalOraclePredictionMarketsResult,
) -> RuntimePredictionMarketsLookupResult:
    return RuntimePredictionMarketsLookupResult(
        query=result.query,
        events=[_map_prediction_market_event(event) for event in result.events],
        warnings=list(result.warnings),
    )


def map_sec_filings_result(
    result: DigitalOracleSecFilingsResult,
) -> RuntimeSecFilingsLookupResult:
    return RuntimeSecFilingsLookupResult(
        ticker=result.ticker,
        cik=result.cik,
        entity_name=result.entity_name,
        filings=[_map_sec_filing(filing) for filing in result.filings],
        warnings=list(result.warnings),
    )


def map_market_sentiment_result(
    result: DigitalOracleMarketSentimentResult,
) -> RuntimeMarketSentimentLookupResult:
    return RuntimeMarketSentimentLookupResult(
        indicator=result.indicator,
        as_of_date=result.as_of_date,
        provider=result.provider,
        score=result.score,
        label=result.label,
        previous_close=result.previous_close,
        week_ago=result.week_ago,
        month_ago=result.month_ago,
        year_ago=result.year_ago,
        source_url=result.source_url,
        warnings=list(result.warnings),
    )


def _map_prediction_market_event(
    event: DigitalOraclePredictionMarketEvent,
) -> RuntimePredictionMarketEvent:
    return RuntimePredictionMarketEvent(
        venue=event.venue,
        event_id=event.event_id,
        title=event.title,
        status=event.status,
        url=event.url,
        end_date=event.end_date,
        contracts=[_map_prediction_market_contract(contract) for contract in event.contracts],
    )


def _map_prediction_market_contract(
    contract: DigitalOraclePredictionMarketContract,
) -> RuntimePredictionMarketContract:
    return RuntimePredictionMarketContract(
        contract_id=contract.contract_id,
        title=contract.title,
        probability=contract.probability,
        yes_price=contract.yes_price,
        no_price=contract.no_price,
        volume=contract.volume,
        open_interest=contract.open_interest,
    )


def _map_sec_filing(filing: DigitalOracleSecFiling) -> RuntimeSecFiling:
    return RuntimeSecFiling(
        accession_number=filing.accession_number,
        form_type=filing.form_type,
        filing_date=filing.filing_date,
        accepted_at=filing.accepted_at,
        primary_document=filing.primary_document,
        url=filing.url,
        description=filing.description,
    )


__all__ = [
    "map_market_sentiment_result",
    "map_prediction_markets_result",
    "map_sec_filings_result",
]
