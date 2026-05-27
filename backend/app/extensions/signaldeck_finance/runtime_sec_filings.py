from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Protocol, cast

import httpx

from app.agents.runtime_tools.types import (
    RuntimeToolContext,
    RuntimeToolError,
    RuntimeToolSpec,
    RuntimeToolWarning,
)
from app.core.config import Settings
from app.core.formatting import normalize_symbol, to_utc
from app.extensions.signaldeck_finance.digital_oracle.factory import (
    create_digital_oracle_phase1_provider_bundle,
    create_sec_filings_provider,
)
from app.extensions.signaldeck_finance.digital_oracle.mappers import map_sec_filings_result
from app.extensions.signaldeck_finance.digital_oracle.service import DigitalOraclePhase1Service
from app.extensions.signaldeck_finance.digital_oracle.types import (
    DigitalOracleProviderError,
    DigitalOracleSecFiling,
    DigitalOracleSecFilingsProvider,
    DigitalOracleSecFilingsProviderQuery,
    DigitalOracleSecFilingsProviderResult,
    DigitalOracleSecFilingsQuery,
)
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_DENIED_CODE,
    FINANCE_WORKSPACE_DENIED_MESSAGES,
    FINANCE_WORKSPACE_EXTENSION_KEY,
)
from app.extensions.signaldeck_finance.runtime_types import SEC_FILINGS_LOOKUP_TOOL_KEY

SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_sec_filings_lookup"
SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE = FINANCE_WORKSPACE_DENIED_CODE
SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE = FINANCE_WORKSPACE_DENIED_MESSAGES[
    SEC_FILINGS_LOOKUP_TOOL_KEY
]

_SEC_FILINGS_MAX_ITEM_LIMIT = 50
_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_DOCUMENT_URL_TEMPLATE = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}"
_SEC_FILINGS_LOOKUP_DESCRIPTION = (
    "Read normalized SEC EDGAR filing summaries for one ticker with optional filters."
)
_SEC_FILINGS_LOOKUP_GUIDANCE = (
    "When you need SEC filing facts, call signaldeck_sec_filings_lookup with a ticker "
    "and optional form/date filters. Use only returned filing summaries, disclose warnings "
    "for empty, stale, or config-blocked EDGAR coverage, and never invent filing facts "
    "or ask the model/user for the configured EDGAR contact email."
)
_SEC_FILINGS_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "ticker": {"type": "string", "minLength": 1},
        "formTypes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
        },
        "startDate": {"type": "string"},
        "endDate": {"type": "string"},
        "itemLimit": {"type": "integer", "minimum": 1, "maximum": _SEC_FILINGS_MAX_ITEM_LIMIT},
    },
    "required": ["ticker"],
    "additionalProperties": False,
}


class _EdgarJsonClient(Protocol):
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> object: ...


class _HttpxEdgarJsonClient:
    def get_json(
        self,
        url: str,
        *,
        timeout: float,
        contact_email: str,
    ) -> object:
        headers = {
            "Accept": "application/json",
            "User-Agent": f"signaldeck-backend/0.1 sec-filings ({contact_email})",
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(url, headers=headers)
                _ = response.raise_for_status()
                return cast(object, response.json())
        except httpx.TimeoutException as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR timed out while fetching filings",
                code="provider_timeout",
                details={"provider": "edgar"},
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise _http_status_provider_error(exc) from exc
        except httpx.HTTPError as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR is unavailable for filing lookup",
                code="provider_unavailable",
                details={"provider": "edgar"},
            ) from exc
        except ValueError as exc:
            raise DigitalOracleProviderError(
                "SEC EDGAR returned malformed filing data",
                details={"provider": "edgar"},
            ) from exc


class EdgarSecFilingsProvider:
    provider_name: str = "edgar"

    def __init__(self, http_client: _EdgarJsonClient | None = None) -> None:
        self._http_client: _EdgarJsonClient = http_client or _HttpxEdgarJsonClient()

    def lookup_sec_filings(
        self,
        query: DigitalOracleSecFilingsProviderQuery,
    ) -> DigitalOracleSecFilingsProviderResult:
        company_payload = self._http_client.get_json(
            _COMPANY_TICKERS_URL,
            timeout=query.timeout_seconds,
            contact_email=query.edgar_contact_email,
        )
        company = _company_for_ticker(company_payload, query.ticker)
        if company is None:
            return DigitalOracleSecFilingsProviderResult(
                provider=self.provider_name,
                ticker=query.ticker,
                warnings=(_ticker_not_found_warning(query.ticker),),
            )

        cik = _company_cik(company)
        if cik is None:
            raise DigitalOracleProviderError(
                "SEC EDGAR returned malformed ticker mapping",
                details={"provider": self.provider_name, "ticker": query.ticker},
            )
        submissions_payload = self._http_client.get_json(
            _SUBMISSIONS_URL_TEMPLATE.format(cik=cik),
            timeout=query.timeout_seconds,
            contact_email=query.edgar_contact_email,
        )
        submissions = _mapping_payload(submissions_payload, label="company submissions")
        entity_name = _text(submissions.get("name")) or _text(company.get("title"))
        recent = _recent_filings_payload(submissions)
        warnings: list[RuntimeToolWarning] = []
        filings = _map_recent_filings(recent, cik=cik, warnings=warnings)
        if not filings and _has_archived_filings(submissions):
            warnings.append(_stale_archive_warning(query.ticker, cik=cik))

        return DigitalOracleSecFilingsProviderResult(
            provider=self.provider_name,
            ticker=query.ticker,
            cik=cik,
            entity_name=entity_name,
            filings=tuple(filings),
            warnings=tuple(warnings),
        )


def create_sec_filings_provider_adapter() -> DigitalOracleSecFilingsProvider:
    return EdgarSecFilingsProvider()


def create_sec_filings_service(
    *,
    settings: Settings | None = None,
    sec_filings_provider: DigitalOracleSecFilingsProvider | None = None,
) -> DigitalOraclePhase1Service:
    provider_bundle = replace(
        create_digital_oracle_phase1_provider_bundle(settings),
        sec_filings=create_sec_filings_provider(settings),
    )
    return DigitalOraclePhase1Service(
        provider_bundle=provider_bundle,
        sec_filings_provider=sec_filings_provider or create_sec_filings_provider_adapter(),
    )


def parse_sec_filings_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={"ticker", "formTypes", "startDate", "endDate", "itemLimit"},
        function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    start_date = _parse_optional_date_argument(raw_arguments.get("startDate"), "startDate")
    end_date = _parse_optional_date_argument(raw_arguments.get("endDate"), "endDate")
    _validate_date_bounds(start_date, end_date)
    return {
        "ticker": _parse_required_ticker_argument(raw_arguments.get("ticker")),
        "form_types": _parse_form_types_argument(raw_arguments.get("formTypes")),
        "start_date": start_date,
        "end_date": end_date,
        "item_limit": _parse_optional_integer_argument(
            raw_arguments.get("itemLimit"),
            field_name="itemLimit",
            minimum=1,
            maximum=_SEC_FILINGS_MAX_ITEM_LIMIT,
        ),
    }


def execute_sec_filings_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    del context
    service = create_sec_filings_service()
    result = service.lookup_sec_filings(
        DigitalOracleSecFilingsQuery(
            ticker=cast(str, arguments["ticker"]),
            form_types=cast(tuple[str, ...] | None, arguments["form_types"]),
            start_date=cast(date | None, arguments["start_date"]),
            end_date=cast(date | None, arguments["end_date"]),
            item_limit=cast(int | None, arguments["item_limit"]),
        )
    )
    runtime_result = map_sec_filings_result(result)
    return cast(dict[str, object], runtime_result.model_dump(mode="json", by_alias=True))


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"OpenAI response requested {function_name} with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} arguments must be a JSON object.",
        )
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(
    raw_arguments: dict[str, object],
    *,
    allowed_keys: set[str],
    function_name: str,
) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{function_name} arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )


def _parse_required_ticker_argument(value: object) -> str:
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} ticker is required.",
        )
    normalized = normalize_symbol(value)
    if not normalized:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} ticker must not be empty.",
        )
    return normalized


def _parse_form_types_argument(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                "formTypes must be an array of strings."
            ),
        )
    form_types: list[str] = []
    seen: set[str] = set()
    for raw_form_type in cast(list[object], value):
        if not isinstance(raw_form_type, str):
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    "formTypes must be an array of strings."
                ),
            )
        form_type = raw_form_type.strip().upper()
        if not form_type:
            raise RuntimeToolError(
                code="agent_tool_call_invalid",
                message=(
                    f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                    "formTypes must not contain empty values."
                ),
            )
        if form_type not in seen:
            form_types.append(form_type)
            seen.add(form_type)
    if not form_types:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} "
                "formTypes must contain at least one form type."
            ),
        )
    return tuple(form_types)


def _parse_optional_date_argument(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} " "must be a string date."
            ),
        )
    raw_value = value.strip()
    if not raw_value:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                "must be a valid ISO date."
            ),
        )
    try:
        return date.fromisoformat(raw_value)
    except ValueError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                "must be a valid ISO date."
            ),
        ) from exc


def _validate_date_bounds(start_date: date | None, end_date: date | None) -> None:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} startDate "
                "must be before or equal to endDate."
            ),
        )


def _parse_optional_integer_argument(
    value: object,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} " "must be an integer."
            ),
        )
    if value < minimum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                f"must be at least {minimum}."
            ),
        )
    if value > maximum:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME} {field_name} "
                f"must be at most {maximum}."
            ),
        )
    return int(value)


def _company_for_ticker(payload: object, ticker: str) -> Mapping[str, object] | None:
    rows = _company_rows(payload)
    for row in rows:
        row_ticker = _text(row.get("ticker"))
        if row_ticker is not None and normalize_symbol(row_ticker) == ticker:
            return row
    return None


def _company_rows(payload: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(payload, Mapping):
        values = cast(Mapping[str, object], payload).values()
        return tuple(
            cast(Mapping[str, object], value) for value in values if isinstance(value, Mapping)
        )
    if isinstance(payload, list):
        values = cast(list[object], payload)
        return tuple(
            cast(Mapping[str, object], value) for value in values if isinstance(value, Mapping)
        )
    raise DigitalOracleProviderError(
        "SEC EDGAR returned malformed ticker mapping",
        details={"provider": "edgar"},
    )


def _company_cik(company: Mapping[str, object]) -> str | None:
    raw_cik = company.get("cik_str") or company.get("cik")
    text = _text(raw_cik)
    if text is None:
        return None
    digits = "".join(character for character in text if character.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _mapping_payload(payload: object, *, label: str) -> Mapping[str, object]:
    if not isinstance(payload, Mapping):
        raise DigitalOracleProviderError(
            f"SEC EDGAR returned malformed {label}",
            details={"provider": "edgar"},
        )
    return cast(Mapping[str, object], payload)


def _recent_filings_payload(submissions: Mapping[str, object]) -> Mapping[str, object]:
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        return {}
    filings_payload = cast(Mapping[str, object], filings)
    recent = filings_payload.get("recent")
    if not isinstance(recent, Mapping):
        return {}
    return cast(Mapping[str, object], recent)


def _has_archived_filings(submissions: Mapping[str, object]) -> bool:
    filings = submissions.get("filings")
    if not isinstance(filings, Mapping):
        return False
    filings_payload = cast(Mapping[str, object], filings)
    files = filings_payload.get("files")
    if not isinstance(files, list):
        return False
    return len(cast(list[object], files)) > 0


def _map_recent_filings(
    recent: Mapping[str, object],
    *,
    cik: str,
    warnings: list[RuntimeToolWarning],
) -> list[DigitalOracleSecFiling]:
    filings: list[DigitalOracleSecFiling] = []
    accessions = _sequence_values(recent.get("accessionNumber"))
    for index, raw_accession in enumerate(accessions):
        accession_number = _text(raw_accession)
        form_type = _text_at(recent, "form", index)
        filing_date = _date_at(recent, "filingDate", index)
        if accession_number is None or form_type is None or filing_date is None:
            warnings.append(_malformed_warning("filing row"))
            continue
        primary_document = _text_at(recent, "primaryDocument", index)
        filings.append(
            DigitalOracleSecFiling(
                accession_number=accession_number,
                form_type=form_type.upper(),
                filing_date=filing_date,
                accepted_at=_datetime_at(recent, "acceptanceDateTime", index),
                primary_document=primary_document,
                url=_filing_url(cik, accession_number, primary_document),
                description=(
                    _text_at(recent, "primaryDocDescription", index)
                    or _text_at(recent, "description", index)
                ),
            )
        )
    return filings


def _sequence_values(value: object) -> tuple[object, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(value)
    return ()


def _text_at(payload: Mapping[str, object], key: str, index: int) -> str | None:
    values = _sequence_values(payload.get(key))
    if index >= len(values):
        return None
    return _text(values[index])


def _date_at(payload: Mapping[str, object], key: str, index: int) -> date | None:
    value = _text_at(payload, key, index)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _datetime_at(payload: Mapping[str, object], key: str, index: int) -> datetime | None:
    value = _text_at(payload, key, index)
    if value is None:
        return None
    return _parse_edgar_datetime(value)


def _parse_edgar_datetime(value: str) -> datetime | None:
    iso_value = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        return to_utc(datetime.fromisoformat(iso_value))
    except ValueError:
        compact = value.strip()
        try:
            parsed = datetime.strptime(compact, "%Y%m%d%H%M%S")
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC)


def _filing_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    cik_path = cik.lstrip("0") or cik
    accession_path = accession_number.replace("-", "")
    base_url = _ARCHIVES_DOCUMENT_URL_TEMPLATE.format(cik=cik_path, accession=accession_path)
    if primary_document is None:
        return base_url
    return f"{base_url}/{primary_document}"


def _text(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, int):
        return str(value)
    return None


def _ticker_not_found_warning(ticker: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_ticker_not_found",
        message=f"SEC EDGAR ticker mapping was not found for {ticker}.",
        details={"operation": "sec_filings", "provider": "edgar", "ticker": ticker},
    )


def _malformed_warning(field: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_malformed_payload",
        message=f"SEC EDGAR returned malformed filing {field}.",
        details={"operation": "sec_filings", "provider": "edgar", "field": field},
    )


def _stale_archive_warning(ticker: str, *, cik: str) -> RuntimeToolWarning:
    return RuntimeToolWarning(
        code="sec_filings_stale_archive",
        message=(
            "SEC EDGAR recent filing summaries were empty; older archived filings "
            "are not loaded by this lookup."
        ),
        details={"operation": "sec_filings", "provider": "edgar", "ticker": ticker, "cik": cik},
    )


def _http_status_provider_error(exc: httpx.HTTPStatusError) -> DigitalOracleProviderError:
    status_code = exc.response.status_code
    if status_code == 429:
        return DigitalOracleProviderError(
            "SEC EDGAR rate limited filing lookup",
            code="provider_rate_limited",
            details={"provider": "edgar", "status": str(status_code)},
        )
    if status_code >= 500:
        return DigitalOracleProviderError(
            "SEC EDGAR outage while fetching filings",
            code="provider_unavailable",
            details={"provider": "edgar", "status": str(status_code)},
        )
    return DigitalOracleProviderError(
        "SEC EDGAR failed while fetching filings",
        details={"provider": "edgar", "status": str(status_code)},
    )


SEC_FILINGS_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=SEC_FILINGS_LOOKUP_TOOL_KEY,
    openai_function_name=SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="SEC Filings Lookup",
    description=_SEC_FILINGS_LOOKUP_DESCRIPTION,
    parameters_schema=_SEC_FILINGS_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_SEC_FILINGS_LOOKUP_GUIDANCE,
    sort_order=87,
    denied_code=SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE,
    denied_message=SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_sec_filings_lookup_arguments,
    executor=execute_sec_filings_lookup,
    owner_extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
)


__all__ = [
    "EdgarSecFilingsProvider",
    "SEC_FILINGS_LOOKUP_ACCESS_DENIED_CODE",
    "SEC_FILINGS_LOOKUP_ACCESS_DENIED_MESSAGE",
    "SEC_FILINGS_LOOKUP_OPENAI_FUNCTION_NAME",
    "SEC_FILINGS_LOOKUP_TOOL_SPEC",
    "create_sec_filings_provider_adapter",
    "create_sec_filings_service",
    "execute_sec_filings_lookup",
    "parse_sec_filings_lookup_arguments",
]
