from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.extensions.signaldeck_finance.dependencies import FINANCE_SHARED_SERVICE_OWNERSHIP_MAP
from app.extensions.signaldeck_finance.ownership import (
    FINANCE_WORKSPACE_EXTENSION_KEY,
    FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS,
)
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.schemas.extension import ExtensionToggleRequest
from app.schemas.portfolio import PortfolioCreate
from app.schemas.position import PositionCreate
from app.schemas.text_template import TextTemplateCreate
from app.services.extension_gate import (
    MARKET_DATA_SERVICE_SURFACE,
    PORTFOLIO_SERVICE_SURFACE,
    POSITION_SERVICE_SURFACE,
    TEXT_TEMPLATE_SERVICE_SURFACE,
)
from app.services.extension_service import ExtensionService
from app.services.market_data_service import MarketDataService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import (
    ProviderFundamentals,
    ProviderHistorySeries,
    ProviderInsiderData,
    ProviderNewsResult,
    ProviderOhlcvSeries,
    ProviderQuote,
)
from app.services.run_service import RunService
from app.services.text_template_service import TextTemplateService
from tests.test_workflow_package_runtime_api import (
    _drain_run_queue,
    _RuntimeRecordingOpenAIClient,
    _seed_model_connection,
    _wait_for_run,
)


def _finance_tool_package_source(package_key: str) -> str:
    return f"""apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: {package_key}
  name: Finance Matrix Package
  description: Lifecycle matrix fixture.
spec:
  inputs:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles:
    - key: quote_tools
      name: Quote Tools
      toolKeys:
        - signaldeck.market_data.quote_lookup
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        additionalProperties: false
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: finance_analyst
      name: Finance Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        additionalProperties: false
        properties:
          ticker:
            type: string
        required: [ticker]
      outputSchema: summary_output
      capabilityProfiles: [quote_tools]
      budgetUsd: "0.10"
  workflows:
    - key: finance_matrix_flow
      name: Finance Matrix Flow
      inputSchema:
        type: object
        additionalProperties: false
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: step
        id: finance_analysis
        slot: analysis
        uses: finance_analyst
        with:
          ticker: ${{{{ inputs.ticker }}}}
      output:
        from: ${{{{ nodes.finance_analysis.outputs.analysis }}}}
"""


def _tool_keys(client: TestClient) -> list[str]:
    response = client.get("/api/tools")
    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    items = cast(list[dict[str, object]], body["items"])
    return [str(item["key"]) for item in items]


def _create_finance_tool_package(client: TestClient, package_key: str) -> dict[str, Any]:
    response = client.post(
        "/api/workflow-packages",
        json={"manifestSource": _finance_tool_package_source(package_key)},
    )
    assert response.status_code == 201, response.json()
    return cast(dict[str, Any], response.json())


def _set_finance_extension(client: TestClient, *, enabled: bool) -> dict[str, object]:
    response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": enabled},
    )
    assert response.status_code == 200, response.json()
    return cast(dict[str, object], response.json())


def _assert_extension_disabled(response: Response, *, surface: str | None = None) -> None:
    assert response.status_code == 403, response.json()
    body = cast(dict[str, object], response.json())
    assert body["code"] == "extension_disabled"
    assert body["message"] == "Extension is disabled"
    details = cast(list[dict[str, object]], body["details"])
    assert details[0]["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    if surface is not None:
        assert details[0]["surface"] == surface


def _blocking_extension_errors(body: dict[str, object]) -> list[dict[str, object]]:
    return [
        error
        for error in cast(list[dict[str, object]], body["blockingErrors"])
        if error.get("code") == "extension_disabled"
    ]


class _LifecycleQuoteProvider:
    provider_name: str = "lifecycle_matrix"

    def __init__(self) -> None:
        self.quote_calls: list[str] = []

    def fetch_symbol_name(self, symbol: str) -> str | None:
        return f"{symbol.upper()} Incorporated"

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        self.quote_calls.append(normalized_symbol)
        return ProviderQuote(
            symbol=normalized_symbol,
            name=f"{normalized_symbol} Incorporated",
            price=Decimal("101.25"),
            previous_close=Decimal("100.00"),
            currency="USD",
            provider=self.provider_name,
            as_of=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        )

    def fetch_history(
        self,
        symbol: str,
        *,
        range_value: str,
        interval: str,
    ) -> ProviderHistorySeries:
        del symbol, range_value, interval
        raise NotImplementedError

    def fetch_ohlcv(
        self,
        symbol: str,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
    ) -> ProviderOhlcvSeries:
        del symbol, start_date, end_date, interval
        raise NotImplementedError

    def fetch_fundamentals(self, symbol: str) -> ProviderFundamentals:
        del symbol
        raise NotImplementedError

    def fetch_news(
        self,
        *,
        symbols: list[str],
        query: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderNewsResult:
        del symbols, query, start_date, end_date, limit
        raise NotImplementedError

    def fetch_insider_transactions(
        self,
        symbol: str,
        *,
        start_date: datetime | None,
        end_date: datetime | None,
        limit: int,
    ) -> ProviderInsiderData:
        del symbol, start_date, end_date, limit
        raise NotImplementedError


def _disable_finance_workspace(session: Session) -> None:
    _ = ExtensionService(session).set_extension_enabled(
        FINANCE_WORKSPACE_EXTENSION_KEY,
        ExtensionToggleRequest(enabled=False),
    )


def _assert_direct_extension_disabled(exc: ApiError, *, surface: str) -> None:
    assert exc.status_code == 403
    assert exc.code == "extension_disabled"
    assert exc.message == "Extension is disabled"
    assert exc.details == [{"extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY, "surface": surface}]


def test_finance_workspace_extension_lifecycle_matrix_covers_restore_paths(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    _RuntimeRecordingOpenAIClient.reset()
    _RuntimeRecordingOpenAIClient.output_text = '{"summary": "restored finance runtime"}'
    monkeypatch.setattr("app.services.run_service.OpenAI", _RuntimeRecordingOpenAIClient)
    monkeypatch.setattr(RunService, "_dispatch_queue_worker", lambda self: None)
    _seed_model_connection(session_factory)

    enabled_tool_keys = _tool_keys(client)
    assert set(enabled_tool_keys) == set(FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS)

    portfolio = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Lifecycle Matrix Portfolio",
            "slug": "lifecycle_matrix_portfolio",
            "description": "Parity fixture",
            "baseCurrency": "USD",
        },
    )
    assert portfolio.status_code == 201, portfolio.json()
    template = client.post(
        "/api/v1/templates",
        json={"name": "Lifecycle Matrix Template", "content": "# Matrix\n\n{{inputs.ticker}}"},
    )
    assert template.status_code == 201, template.json()
    report = client.post(
        f"/api/v1/reports/compile/{template.json()['id']}",
        json={"inputs": {"ticker": "MSFT"}},
    )
    assert report.status_code == 201, report.json()

    package = _create_finance_tool_package(client, "finance_matrix_package")
    preflight = client.post(
        f"/api/workflow-packages/{package['id']}/preflight",
        params={"workflowKey": "finance_matrix_flow"},
    )
    assert preflight.status_code == 200, preflight.json()
    assert preflight.json()["ready"] is True
    assert preflight.json()["blockingErrors"] == []

    launch = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "finance_matrix_flow",
            "parameters": {"ticker": "MSFT"},
        },
    )
    assert launch.status_code == 201, launch.json()
    run_id = int(launch.json()["id"])
    queued_detail = client.get(f"/api/runs/{run_id}")
    assert queued_detail.status_code == 200, queued_detail.json()
    enabled_dependency = cast(
        list[dict[str, object]], queued_detail.json()["extensionDependencies"]
    )[0]
    assert set(enabled_dependency) == {"extensionKey", "surfaces", "fields"}
    assert enabled_dependency["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert "tool.signaldeck.market_data.quote_lookup" in cast(
        list[str],
        enabled_dependency["surfaces"],
    )

    disabled_extension = _set_finance_extension(client, enabled=False)
    assert disabled_extension["enabled"] is False

    assert _tool_keys(client) == []
    _assert_extension_disabled(
        client.get("/api/v1/portfolios"),
        surface="/api/v1/portfolios",
    )
    _assert_extension_disabled(
        client.get(f"/api/v1/templates/{template.json()['id']}"),
        surface="/api/v1/templates",
    )
    _assert_extension_disabled(
        client.get(f"/api/v1/reports/{report.json()['slug']}"),
        surface="/api/v1/reports",
    )

    disabled_preflight = client.post(
        f"/api/workflow-packages/{package['id']}/preflight",
        params={"workflowKey": "finance_matrix_flow"},
    )
    assert disabled_preflight.status_code == 200, disabled_preflight.json()
    disabled_preflight_body = cast(dict[str, object], disabled_preflight.json())
    assert disabled_preflight_body["ready"] is False
    disabled_preflight_errors = _blocking_extension_errors(disabled_preflight_body)
    assert disabled_preflight_errors == [
        {
            "field": "spec.capabilityProfiles.quote_tools.toolKeys[0]",
            "issue": (
                "Server-declared tool 'signaldeck.market_data.quote_lookup' is disabled because "
                "extension 'signaldeck.finance' is disabled"
            ),
            "code": "extension_disabled",
            "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
            "surface": "tool.signaldeck.market_data.quote_lookup",
        }
    ]

    disabled_launch = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "finance_matrix_flow",
            "parameters": {"ticker": "MSFT"},
        },
    )
    assert disabled_launch.status_code == 422, disabled_launch.json()
    disabled_launch_body = cast(dict[str, object], disabled_launch.json())
    assert disabled_launch_body["code"] == "validation_error"
    launch_details = cast(list[dict[str, object]], disabled_launch_body["details"])
    assert any(
        detail.get("code") == "extension_disabled"
        and detail.get("extensionKey") == FINANCE_WORKSPACE_EXTENSION_KEY
        and detail.get("surface") == "tool.signaldeck.market_data.quote_lookup"
        for detail in launch_details
    )

    with session_factory() as session:
        RunService(session, session_factory).execute_run(run_id)

    failed_detail = client.get(f"/api/runs/{run_id}")
    assert failed_detail.status_code == 200, failed_detail.json()
    failed_body = failed_detail.json()
    assert failed_body["status"] == "failed"
    assert failed_body["error"] == "Extension is disabled"
    failed_dependency = cast(list[dict[str, object]], failed_body["extensionDependencies"])[0]
    assert set(failed_dependency) == {"extensionKey", "surfaces", "fields"}
    assert "tool.signaldeck.market_data.quote_lookup" in cast(
        list[str],
        failed_dependency["surfaces"],
    )

    with session_factory() as session:
        persisted_template = session.get(TextTemplate, template.json()["id"])
        persisted_report = session.get(Report, report.json()["id"])
        assert persisted_template is not None
        assert persisted_report is not None
        assert persisted_template.content == "# Matrix\n\n{{inputs.ticker}}"
        assert persisted_report.slug == report.json()["slug"]
        assert persisted_report.content == report.json()["content"]

    restored_extension = _set_finance_extension(client, enabled=True)
    assert restored_extension["enabled"] is True
    assert _tool_keys(client) == enabled_tool_keys

    restored_portfolios = client.get("/api/v1/portfolios")
    assert restored_portfolios.status_code == 200, restored_portfolios.json()
    restored_portfolio_items = cast(list[dict[str, object]], restored_portfolios.json())
    assert any(item["slug"] == "lifecycle_matrix_portfolio" for item in restored_portfolio_items)
    restored_report = client.get(f"/api/v1/reports/{report.json()['slug']}")
    assert restored_report.status_code == 200, restored_report.json()
    assert restored_report.json()["content"] == report.json()["content"]

    restored_preflight = client.post(
        f"/api/workflow-packages/{package['id']}/preflight",
        params={"workflowKey": "finance_matrix_flow"},
    )
    assert restored_preflight.status_code == 200, restored_preflight.json()
    assert restored_preflight.json()["ready"] is True
    assert restored_preflight.json()["blockingErrors"] == []

    restored_launch = client.post(
        f"/api/workflow-packages/{package['id']}/launches",
        json={
            "version": 1,
            "workflowKey": "finance_matrix_flow",
            "parameters": {"ticker": "NVDA"},
        },
    )
    assert restored_launch.status_code == 201, restored_launch.json()
    restored_run_id = int(restored_launch.json()["id"])

    _drain_run_queue(session_factory)
    restored_detail = _wait_for_run(client, restored_run_id)

    assert restored_detail["status"] == "succeeded"
    assert restored_detail["finalOutput"] == {"summary": "restored finance runtime"}
    restored_dependency = cast(list[dict[str, object]], restored_detail["extensionDependencies"])[0]
    assert set(restored_dependency) == {"extensionKey", "surfaces", "fields"}
    assert restored_dependency["extensionKey"] == FINANCE_WORKSPACE_EXTENSION_KEY
    assert "tool.signaldeck.market_data.quote_lookup" in cast(
        list[str],
        restored_dependency["surfaces"],
    )


def test_finance_shared_service_ownership_map_classifies_task_5_services() -> None:
    expected_services = {
        "MarketDataService",
        "PositionService",
        "PortfolioService",
        "BalanceService",
        "TradingOperationService",
        "CsvImportService",
        "TextTemplateService",
        "ReportService",
        "TemplateCompilerService",
        "MemoryService",
        "MemoryReportService",
        "MemoryContextService",
        "MemoryFollowUpService",
        "ReflectionService",
        "ReturnResolutionService",
        "ReportBackedMemoryStore",
    }
    ownership_by_service = {
        entry.service_name: entry for entry in FINANCE_SHARED_SERVICE_OWNERSHIP_MAP
    }

    assert set(ownership_by_service) == expected_services
    assert {entry.classification for entry in ownership_by_service.values()} == {
        "keep-shared-behind-neutral-seam"
    }
    assert ownership_by_service["MarketDataService"].surface == MARKET_DATA_SERVICE_SURFACE
    assert ownership_by_service["PositionService"].surface == POSITION_SERVICE_SURFACE
    assert ownership_by_service["PortfolioService"].surface == PORTFOLIO_SERVICE_SURFACE
    assert ownership_by_service["TextTemplateService"].surface == TEXT_TEMPLATE_SERVICE_SURFACE


def test_direct_market_data_positions_portfolio_template_services_block_when_disabled(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = _LifecycleQuoteProvider()
    with session_factory() as session:
        portfolio = PortfolioService(session).create_portfolio(
            PortfolioCreate(
                name="Direct Service Matrix",
                slug="direct_service_matrix",
                description="Direct service disabled-state fixture",
                base_currency="USD",
            )
        )
        _ = PositionService(session).create_position(
            portfolio.id,
            PositionCreate(
                symbol="NVDA",
                name="NVIDIA Corporation",
                quantity=Decimal("2"),
                average_cost=Decimal("100.00"),
            ),
        )
        _ = TextTemplateService(session).create_template(
            TextTemplateCreate(name="Direct Service Template", content="{{inputs.ticker}}")
        )
        _disable_finance_workspace(session)

        with pytest.raises(ApiError) as market_data_error:
            _ = MarketDataService(
                session=session,
                quote_provider=quote_provider,
            ).get_quote_snapshot(" nvda ")
        with pytest.raises(ApiError) as positions_error:
            _ = PositionService(session).list_positions(portfolio.id)
        with pytest.raises(ApiError) as portfolio_error:
            _ = PortfolioService(session).list_portfolios()
        with pytest.raises(ApiError) as template_error:
            _ = TextTemplateService(session).list_templates()

    _assert_direct_extension_disabled(
        market_data_error.value,
        surface=MARKET_DATA_SERVICE_SURFACE,
    )
    _assert_direct_extension_disabled(positions_error.value, surface=POSITION_SERVICE_SURFACE)
    _assert_direct_extension_disabled(portfolio_error.value, surface=PORTFOLIO_SERVICE_SURFACE)
    _assert_direct_extension_disabled(template_error.value, surface=TEXT_TEMPLATE_SERVICE_SURFACE)
    assert quote_provider.quote_calls == []


def test_direct_market_data_positions_portfolio_template_services_work_when_enabled(
    session_factory: sessionmaker[Session],
) -> None:
    quote_provider = _LifecycleQuoteProvider()
    with session_factory() as session:
        portfolio = PortfolioService(session).create_portfolio(
            PortfolioCreate(
                name="Enabled Direct Service Matrix",
                slug="enabled_direct_service_matrix",
                description="Direct service enabled-state fixture",
                base_currency="USD",
            )
        )
        _ = PositionService(session).create_position(
            portfolio.id,
            PositionCreate(
                symbol="NVDA",
                name="NVIDIA Corporation",
                quantity=Decimal("2"),
                average_cost=Decimal("100.00"),
            ),
        )
        _ = TextTemplateService(session).create_template(
            TextTemplateCreate(name="Enabled Direct Service Template", content="{{inputs.ticker}}")
        )
        quote, warnings = MarketDataService(
            session=session,
            quote_provider=quote_provider,
        ).get_quote_snapshot(" nvda ")
        positions = PositionService(session).list_positions(portfolio.id)
        portfolios = PortfolioService(session).list_portfolios()
        templates = TextTemplateService(session).list_templates()

    assert quote is not None
    assert quote.symbol == "NVDA"
    assert warnings == []
    assert quote_provider.quote_calls == ["NVDA"]
    assert [position.symbol for position in positions] == ["NVDA"]
    assert [item.slug for item in portfolios] == ["enabled_direct_service_matrix"]
    assert [item.name for item in templates] == ["Enabled Direct Service Template"]
