from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_quote_provider
from app.core.errors import ApiError
from app.db.session import init_db, validate_supported_database_engine
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY
from app.models.market_quote import MarketQuote
from app.models.report import Report
from app.models.symbol_name_cache import SymbolNameCache
from app.models.text_template import TextTemplate
from app.schemas.model_connection import ModelConnectionCreate, ModelConnectionUpdate
from app.services.quote_provider import (
    ProviderHistoryPoint,
    ProviderHistorySeries,
    ProviderQuote,
    QuoteProviderError,
)
from app.services.report_service import ReportService

UTC_TZ = timezone.utc  # noqa: UP017
_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def _assert_logfire_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_ID_PATTERN.fullmatch(value) is not None


class UnsupportedEngine:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = DefaultDialect()
        self.dialect.name = dialect_name


def portfolio_slug_for_name(name: str) -> str:
    return "_".join(name.strip().lower().replace("-", " ").split()) or "portfolio"


def create_portfolio(
    client: TestClient,
    *,
    name: str = "Core Portfolio",
    slug: str | None = None,
) -> dict[str, object]:
    response = client.post(
        "/api/v1/portfolios",
        json={
            "name": name,
            "slug": slug or portfolio_slug_for_name(name),
            "description": f"{name} description",
            "baseCurrency": "USD",
        },
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_balance(
    client: TestClient,
    portfolio_id: str,
    *,
    label: str = "Cash",
    amount: str = "1000.00",
    operation_type: str = "DEPOSIT",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/balances",
        json={"label": label, "amount": amount, "operationType": operation_type},
    )
    assert response.status_code == 201
    return response.json()


def create_position(
    client: TestClient,
    portfolio_id: str,
    *,
    symbol: str = "AAPL",
    quantity: str = "10",
    average_cost: str = "185.50",
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": symbol,
            "name": f"{symbol} Holdings",
            "quantity": quantity,
            "averageCost": average_cost,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_template(
    client: TestClient,
    *,
    name: str = "Daily Summary",
    content: str = "# Summary\n\n{{portfolios}}",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def insert_report_row(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    slug: str,
    source: str,
    content: str = "# Report",
    metadata: dict[str, object] | None = None,
) -> int:
    with session_factory() as session:
        report = Report(
            name=name,
            slug=slug,
            source=source,
            content=content,
            metadata_=metadata or {},
        )
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
        return report_id


def test_agent_platform_routes_mount_package_first_api_without_global_authoring_routes(
    app: FastAPI,
) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert {
        "/api/workflow-packages",
        "/api/workflow-packages/{package_id}",
        "/api/workflow-packages/{package_id}/launch",
        "/api/workflow-packages/{package_id}/launches",
        "/api/model-connections",
        "/api/tools",
        "/api/runs",
        "/api/runs/{run_id}",
    } <= route_paths
    assert all(
        not path.startswith(prefix)
        for path in route_paths
        for prefix in (
            "/api/agents",
            "/api/capabilities",
            "/api/mcp-servers",
            "/api/output-schemas",
            "/api/workflows",
        )
    )
    assert not any(path.startswith("/api/v3") for path in route_paths)


def test_agent_platform_removed_global_authoring_routes_return_404(client: TestClient) -> None:
    removed_paths = [
        "/api/agents",
        "/api/capabilities",
        "/api/mcp-servers",
        "/api/output-schemas",
        "/api/workflows",
        "/api/agents/1/test-panel",
    ]

    for path in removed_paths:
        assert client.get(path).status_code == 404
        assert client.post(path, json={}).status_code == 404


def test_finance_workspace_product_routes_remain_mounted_for_portfolio_template_report_market_data(
    app: FastAPI,
) -> None:
    route_paths = {route.path for route in app.routes if isinstance(route, APIRoute)}

    assert {
        "/api/v1/portfolios",
        "/api/v1/portfolios/{portfolio_id}/balances",
        "/api/v1/portfolios/{portfolio_id}/positions",
        "/api/v1/portfolios/{portfolio_id}/trading-operations",
        "/api/v1/portfolios/{portfolio_id}/market-data/quotes",
        "/api/v1/templates",
        "/api/v1/reports",
    } <= route_paths


@pytest.mark.parametrize(
    ("path", "surface"),
    [
        ("/api/v1/portfolios", "/api/v1/portfolios"),
        ("/api/v1/portfolios/1/balances", "/api/v1/portfolios/{portfolio_id}/balances"),
        ("/api/v1/portfolios/1/positions", "/api/v1/portfolios/{portfolio_id}/positions"),
        (
            "/api/v1/portfolios/1/trading-operations",
            "/api/v1/portfolios/{portfolio_id}/trading-operations",
        ),
        (
            "/api/v1/portfolios/1/market-data/quotes?symbols=AAPL",
            "/api/v1/portfolios/{portfolio_id}/market-data",
        ),
        ("/api/v1/templates", "/api/v1/templates"),
        ("/api/v1/reports", "/api/v1/reports"),
    ],
)
def test_disabled_finance_workspace_portfolio_template_report_market_data_routes_return_403(
    client: TestClient,
    path: str,
    surface: str,
) -> None:
    toggle_response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert toggle_response.status_code == 200, toggle_response.json()

    response = client.get(path)

    assert response.status_code == 403, response.json()
    assert response.json() == {
        "code": "extension_disabled",
        "message": "Extension is disabled",
        "details": [
            {
                "extensionKey": FINANCE_WORKSPACE_EXTENSION_KEY,
                "surface": surface,
            }
        ],
    }


def test_disabled_finance_workspace_preserves_template_and_report_rows(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    template = create_template(
        client,
        name="Disabled Data Safety",
        content="# Data safety\n\n{{reports}}",
    )
    report_response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert report_response.status_code == 201, report_response.json()
    report = report_response.json()

    toggle_response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": False},
    )
    assert toggle_response.status_code == 200, toggle_response.json()

    blocked_paths = (
        "/api/v1/templates",
        "/api/v1/templates/placeholders",
        f"/api/v1/templates/{template['id']}/compile",
        "/api/v1/reports",
        f"/api/v1/reports/{report['slug']}",
        f"/api/v1/reports/{report['slug']}/download",
    )
    for path in blocked_paths:
        response = client.get(path)
        assert response.status_code == 403, response.json()
        assert response.json()["code"] == "extension_disabled"

    mutation_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Mutated while disabled"},
    )
    assert mutation_response.status_code == 403, mutation_response.json()

    with session_factory() as session:
        persisted_template = session.get(TextTemplate, template["id"])
        persisted_report = session.get(Report, report["id"])
        assert persisted_template is not None
        assert persisted_report is not None
        assert persisted_template.content == "# Data safety\n\n{{reports}}"
        assert persisted_report.content == report["content"]
        assert persisted_report.slug == report["slug"]
        assert persisted_report.source == "compiled"

    reenable_response = client.patch(
        f"/api/extensions/{FINANCE_WORKSPACE_EXTENSION_KEY}",
        json={"enabled": True},
    )
    assert reenable_response.status_code == 200, reenable_response.json()
    restored_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert restored_response.status_code == 200, restored_response.json()
    assert restored_response.json()["content"] == report["content"]


def test_agent_platform_runs_target_filters_require_target_kind(client: TestClient) -> None:
    response = client.get("/api/runs", params={"targetId": 1})

    assert response.status_code == 422, response.json()
    assert response.json() == {
        "code": "validation_error",
        "message": "Request validation failed",
        "details": [
            {
                "field": "targetKind",
                "issue": (
                    "targetKind is required when targetId, targetKey, or targetVersion is provided"
                ),
            }
        ],
    }


_DELETED_MODEL_CONNECTION_FIELDS: dict[str, object] = {
    "organization": "legacy-org",
    "project": "legacy-project",
    "organizationProject": "legacy-org-project",
    "organization_project": "legacy_org_project",
    "projectId": "legacy-project-id",
}


def _model_connection_create_payload() -> dict[str, object]:
    return {
        "key": "deleted_fields_model",
        "name": "Deleted Fields Model",
        "description": "Model connection without removed fields.",
        "baseUrl": "https://api.openai.com/v1",
        "modelId": "gpt-5.5-mini",
        "reasoningEffort": "medium",
        "apiStyle": "responses",
        "timeoutSeconds": 60,
        "apiKey": "sk-test-model-connection",
    }


def _assert_deleted_model_connection_fields_rejected(
    response: Response,
    field_names: set[str],
) -> None:
    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    detail_items = cast(list[dict[str, str]], body["details"])
    details = {detail["field"]: detail["issue"] for detail in detail_items}
    assert field_names <= details.keys()
    for field_name in field_names:
        assert details[field_name] == "Extra inputs are not permitted"


def _assert_schema_extra_forbidden(
    schema_type: type[ModelConnectionCreate] | type[ModelConnectionUpdate],
    payload: dict[str, object],
    field_names: set[str],
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _ = schema_type.model_validate(payload)

    extra_error_types = {
        str(error["loc"][0]): error["type"]
        for error in excinfo.value.errors()
        if error["type"] == "extra_forbidden"
    }
    expected_error_types = {field_name: "extra_forbidden" for field_name in field_names}
    assert expected_error_types.items() <= extra_error_types.items()


def test_model_connection_create_rejects_deleted_organization_project_fields(
    client: TestClient,
) -> None:
    payload = {**_model_connection_create_payload(), **_DELETED_MODEL_CONNECTION_FIELDS}

    response = client.post("/api/model-connections", json=payload)

    field_names = set(_DELETED_MODEL_CONNECTION_FIELDS)
    _assert_deleted_model_connection_fields_rejected(response, field_names)
    _assert_schema_extra_forbidden(ModelConnectionCreate, payload, field_names)


def test_model_connection_update_rejects_deleted_organization_project_fields(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_create_payload(),
    )
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    connection_id = cast(int, create_body["id"])
    payload: dict[str, object] = {
        "description": "Attempted update should not persist.",
        **_DELETED_MODEL_CONNECTION_FIELDS,
    }

    response = client.patch(f"/api/model-connections/{connection_id}", json=payload)

    field_names = set(_DELETED_MODEL_CONNECTION_FIELDS)
    _assert_deleted_model_connection_fields_rejected(response, field_names)
    _assert_schema_extra_forbidden(ModelConnectionUpdate, payload, field_names)
    unchanged_response = client.get(f"/api/model-connections/{connection_id}")
    assert unchanged_response.status_code == 200, unchanged_response.json()
    unchanged_body = cast(dict[str, object], unchanged_response.json())
    assert unchanged_body["description"] == "Model connection without removed fields."


def test_portfolio_isolation_and_summary_counts(client: TestClient) -> None:
    first = create_portfolio(client, name="Core")
    second = create_portfolio(client, name="Sandbox")

    create_balance(client, str(first["id"]), label="Core Cash", amount="25000.00")
    create_position(client, str(second["id"]), symbol="MSFT", quantity="5", average_cost="400.00")

    first_balances = client.get(f"/api/v1/portfolios/{first['id']}/balances")
    second_balances = client.get(f"/api/v1/portfolios/{second['id']}/balances")
    first_positions = client.get(f"/api/v1/portfolios/{first['id']}/positions")
    second_positions = client.get(f"/api/v1/portfolios/{second['id']}/positions")

    assert first_balances.status_code == 200
    assert second_balances.status_code == 200
    assert first_positions.status_code == 200
    assert second_positions.status_code == 200

    assert len(first_balances.json()) == 1
    assert second_balances.json() == []
    assert first_positions.json() == []
    assert len(second_positions.json()) == 1

    portfolios = client.get("/api/v1/portfolios")
    assert portfolios.status_code == 200
    portfolio_map = {item["id"]: item for item in portfolios.json()}
    assert portfolio_map[first["id"]]["slug"] == "core"
    assert portfolio_map[second["id"]]["slug"] == "sandbox"
    assert portfolio_map[first["id"]]["balanceCount"] == 1
    assert portfolio_map[first["id"]]["positionCount"] == 0
    assert portfolio_map[second["id"]]["balanceCount"] == 0
    assert portfolio_map[second["id"]]["positionCount"] == 1


def test_portfolio_slug_validation_uniqueness_and_immutability(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement_account")
    assert portfolio["slug"] == "retirement_account"

    duplicate_response = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Retirement Copy",
            "slug": "retirement_account",
            "description": "Duplicate slug",
            "baseCurrency": "USD",
        },
    )
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["code"] == "duplicate_portfolio_slug"

    invalid_response = client.post(
        "/api/v1/portfolios",
        json={
            "name": "Broken",
            "slug": "123-bad",
            "description": "Invalid slug",
            "baseCurrency": "USD",
        },
    )
    assert invalid_response.status_code == 422
    assert invalid_response.json()["code"] == "validation_error"
    assert invalid_response.json()["details"][0]["field"] == "slug"

    immutable_response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}",
        json={"slug": "new_slug"},
    )
    assert immutable_response.status_code == 422
    assert immutable_response.json()["code"] == "validation_error"
    assert immutable_response.json()["details"][0]["field"] == "slug"


def test_balance_crud(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    balance = create_balance(client, portfolio_id, label="Reserve", amount="1500.00")
    balance_id = str(balance["id"])

    list_response = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert list_response.status_code == 200
    assert list_response.json()[0]["label"] == "Reserve"

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/balances/{balance_id}",
        json={"label": "Trading Cash", "amount": "1750.00"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Trading Cash"
    assert Decimal(update_response.json()["amount"]) == Decimal("1750.00")

    delete_response = client.delete(f"/api/v1/portfolios/{portfolio_id}/balances/{balance_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_position_crud(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    position = create_position(client, portfolio_id)
    position_id = str(position["id"])

    list_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert list_response.status_code == 200
    assert list_response.json()[0]["symbol"] == "AAPL"

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}",
        json={"quantity": "12", "averageCost": "184.10", "name": "Apple Inc."},
    )
    assert update_response.status_code == 200
    assert Decimal(update_response.json()["quantity"]) == Decimal("12")
    assert Decimal(update_response.json()["averageCost"]) == Decimal("184.10")
    assert update_response.json()["name"] == "Apple Inc."

    delete_response = client.delete(f"/api/v1/portfolios/{portfolio_id}/positions/{position_id}")
    assert delete_response.status_code == 204

    after_delete = client.get(f"/api/v1/portfolios/{portfolio_id}/positions")
    assert after_delete.status_code == 200
    assert after_delete.json() == []


def test_template_crud_and_compile_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement")
    create_portfolio(client, name="Income", slug="income")
    create_balance(client, str(portfolio["id"]), label="Cash", amount="1500.00")
    create_balance(
        client,
        str(portfolio["id"]),
        label="Taxes",
        amount="250.00",
        operation_type="WITHDRAWAL",
    )
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )
    create_position(
        client, str(portfolio["id"]), symbol="MSFT", quantity="5", average_cost="400.00"
    )

    template = create_template(
        client,
        name="Retirement Summary",
        content=(
            "# Summary\n\n"
            "Slug: {{portfolios.retirement.slug}}\n"
            "Balance: {{portfolios.retirement.balance}}\n"
            "Balance amount: {{portfolios.retirement.balance.amount}}\n"
            "Positions:\n{{portfolios.retirement.positions}}\n\n"
            "Apple name: {{portfolios.retirement.positions.AAPL.name}}\n\n"
            "All portfolios:\n{{portfolios}}"
        ),
    )

    list_response = client.get("/api/v1/templates")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [template["id"]]

    get_response = client.get(f"/api/v1/templates/{template['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Retirement Summary"

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert "Slug: retirement" in compiled
    assert "Balance: 1250.0000 USD" in compiled
    assert "Balance amount: 1250.0000" in compiled
    assert "- AAPL (AAPL Holdings): 10.00000000 shares @ 185.50000000 USD" in compiled
    assert "- MSFT (MSFT Holdings): 5.00000000 shares @ 400.00000000 USD" in compiled
    assert "Apple name: AAPL Holdings" in compiled
    assert "## Income" in compiled
    assert "## Retirement" in compiled

    update_response = client.patch(
        f"/api/v1/templates/{template['id']}",
        json={"name": "Weekly Summary", "content": "# Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Weekly Summary"
    assert update_response.json()["content"] == "# Updated"

    delete_response = client.delete(f"/api/v1/templates/{template['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/templates/{template['id']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


@pytest.mark.parametrize("payload", [{"confirm": False}, {"confirm": True}])
def test_template_seed_route_is_removed(
    client: TestClient,
    payload: dict[str, bool],
) -> None:
    create_portfolio(client, name="Legacy Portfolio", slug="legacy_portfolio")
    create_template(client, name="Legacy Template", content="# Legacy")

    response = client.post("/api/v1/templates/seed", json=payload)

    assert response.status_code == 404

    templates_response = client.get("/api/v1/templates")
    assert templates_response.status_code == 200
    assert [item["name"] for item in templates_response.json()] == ["Legacy Template"]

    portfolios_response = client.get("/api/v1/portfolios")
    assert portfolios_response.status_code == 200
    assert [item["slug"] for item in portfolios_response.json()] == ["legacy_portfolio"]


def test_template_compile_accepts_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Reusable", slug="reusable")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )
    create_position(
        client, str(portfolio["id"]), symbol="TSLA", quantity="6", average_cost="210.00"
    )

    aapl_report = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Saved Analysis",
            "content": "AAPL prior view",
            "metadata": {
                "tags": ["aapl_loop"],
                "analysis": {"ticker": "AAPL"},
            },
        },
    )
    assert aapl_report.status_code == 201

    tsla_report = client.post(
        "/api/v1/reports",
        json={
            "name": "TSLA Saved Analysis",
            "content": "TSLA prior view",
            "metadata": {
                "tags": ["tsla_loop"],
                "analysis": {"ticker": "TSLA"},
            },
        },
    )
    assert tsla_report.status_code == 201

    template = create_template(
        client,
        name="Reusable Loop Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
            "Quantity: {{portfolios.by_slug(inputs.portfolio_slug).positions."
            "by_symbol(inputs.ticker).quantity}}\n"
            "Tagged prior: {{reports.by_tag(inputs.analysis_tag).latest.name}}\n"
            "Latest ticker analysis: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    inline_aapl = client.post(
        "/api/v1/templates/compile",
        json={
            "content": template["content"],
            "inputs": {
                "portfolio_slug": "reusable",
                "ticker": "AAPL",
                "analysis_tag": "aapl_loop",
            },
        },
    )
    assert inline_aapl.status_code == 200
    assert inline_aapl.json()["compiled"] == (
        "Ticker: AAPL\n"
        "Portfolio: Reusable\n"
        "Quantity: 10.00000000\n"
        "Tagged prior: AAPL Saved Analysis\n"
        "Latest ticker analysis: AAPL prior view"
    )

    stored_tsla = client.post(
        f"/api/v1/templates/{template['id']}/compile",
        json={
            "inputs": {
                "portfolio_slug": "reusable",
                "ticker": "TSLA",
                "analysis_tag": "tsla_loop",
            }
        },
    )
    assert stored_tsla.status_code == 200
    assert stored_tsla.json()["compiled"] == (
        "Ticker: TSLA\n"
        "Portfolio: Reusable\n"
        "Quantity: 6.00000000\n"
        "Tagged prior: TSLA Saved Analysis\n"
        "Latest ticker analysis: TSLA prior view"
    )


def test_template_compile_surfaces_missing_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Missing Inputs", slug="missing_inputs")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="4", average_cost="150.00"
    )

    response = client.post(
        "/api/v1/templates/compile",
        json={
            "content": (
                "Ticker: {{inputs.ticker}}\n"
                "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
                "Latest: {{reports.latest(inputs.ticker).name}}"
            ),
            "inputs": {"portfolio_slug": "missing_inputs"},
        },
    )

    assert response.status_code == 200
    assert response.json()["compiled"] == (
        "Ticker: [Missing input: ticker]\n"
        "Portfolio: Missing Inputs\n"
        "Latest: [Missing input: ticker]"
    )


def test_template_metric_placeholders_with_quotes(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    portfolio_id = str(portfolio["id"])
    create_balance(client, portfolio_id, label="Cash", amount="1500.00")
    create_balance(
        client, portfolio_id, label="Taxes", amount="250.00", operation_type="WITHDRAWAL"
    )
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")
    create_position(client, portfolio_id, symbol="MSFT", quantity="5", average_cost="400.00")

    template = create_template(
        client,
        name="Metrics Report",
        content=(
            "Total: {{portfolios.growth.total_value}}\n"
            "PnL: {{portfolios.growth.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.growth.positions.AAPL.market_value}}\n"
            "AAPL PnL: {{portfolios.growth.positions.AAPL.unrealized_pnl}}\n"
            "AAPL Pct: {{portfolios.growth.positions.AAPL.unrealized_pnl_percent}}\n"
            "MSFT MV: {{portfolios.growth.positions.MSFT.market_value}}\n"
            "Slug: {{portfolios.growth.slug}}\n"
            "Balance: {{portfolios.growth.balance.amount}}"
        ),
    )

    provider = StableQuoteProvider()
    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled == (
        "Total: 4118.6000000000\n"
        "PnL: -986.4000000000000000\n"
        "AAPL MV: 1912.4000000000\n"
        "AAPL PnL: 57.4000000000000000\n"
        "AAPL Pct: 0.03094339622641509433962264151\n"
        "MSFT MV: 956.2000000000\n"
        "Slug: growth\n"
        "Balance: 1250.0000"
    )


def test_template_metric_placeholders_batch_quote_fetches_once_per_compile(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client, name="Cached", slug="cached")
    portfolio_id = str(portfolio["id"])
    create_balance(client, portfolio_id, label="Cash", amount="1500.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")
    create_position(client, portfolio_id, symbol="MSFT", quantity="5", average_cost="400.00")

    template = create_template(
        client,
        name="Cached Metrics",
        content=(
            "Total: {{portfolios.cached.total_value}}\n"
            "PnL: {{portfolios.cached.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.cached.positions.AAPL.market_value}}\n"
            "AAPL PnL: {{portfolios.cached.positions.AAPL.unrealized_pnl}}\n"
            "MSFT MV: {{portfolios.cached.positions.MSFT.market_value}}"
        ),
    )

    provider = CountingQuoteProvider()
    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    assert provider.quote_calls == 2


def test_template_metric_placeholders_with_broken_provider(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Broken", slug="broken")
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="185.50")

    template = create_template(
        client,
        name="Broken Metrics",
        content=(
            "Total: {{portfolios.broken.total_value}}\n"
            "PnL: {{portfolios.broken.unrealized_pnl}}\n"
            "AAPL MV: {{portfolios.broken.positions.AAPL.market_value}}\n"
            "Name: {{portfolios.broken.name}}"
        ),
    )

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: BrokenQuoteProvider()

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Total: \n" in compiled
    assert "PnL: \n" in compiled
    assert "AAPL MV: \n" in compiled
    assert "Name: Broken" in compiled


def test_template_metric_zero_cost_basis_percent(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Zero", slug="zero")
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="10", average_cost="0")

    template = create_template(
        client,
        name="Zero Cost",
        content="Pct: {{portfolios.zero.positions.AAPL.unrealized_pnl_percent}}",
    )

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: StableQuoteProvider()

    compile_response = client.get(f"/api/v1/templates/{template['id']}/compile")
    application.dependency_overrides.clear()

    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert compiled == "Pct: "


def test_nullable_patch_fields_can_be_cleared(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    clear_description = client.patch(
        f"/api/v1/portfolios/{portfolio_id}",
        json={"description": None},
    )
    assert clear_description.status_code == 200
    assert clear_description.json()["description"] is None

    position = create_position(
        client, portfolio_id, symbol="NVDA", quantity="3", average_cost="700.00"
    )
    clear_position_name = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/positions/{position['id']}",
        json={"name": None},
    )
    assert clear_position_name.status_code == 200
    assert clear_position_name.json()["name"] is None


def test_csv_preview_and_commit_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    valid_csv = (
        "symbol,quantity,average_cost,name\n"
        "AAPL,10,185.50,Apple Inc.\n"
        "MSFT,5,400.00,Microsoft Corp.\n"
    )
    preview_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/preview",
        files={"file": ("positions.csv", valid_csv, "text/csv")},
    )
    assert preview_response.status_code == 200
    preview_payload = preview_response.json()
    assert preview_payload["mode"] == "upsert"
    assert len(preview_payload["acceptedRows"]) == 2
    assert preview_payload["errors"] == []

    commit_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", valid_csv, "text/csv")},
    )
    assert commit_response.status_code == 200
    commit_payload = commit_response.json()
    assert commit_payload["inserted"] == 2
    assert commit_payload["updated"] == 0
    assert commit_payload["unchanged"] == 0

    updated_csv = (
        "symbol,quantity,average_cost,name\n"
        "AAPL,12,184.10,Apple Inc.\n"
        "MSFT,5,400.00,Microsoft Corp.\n"
    )
    second_commit = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", updated_csv, "text/csv")},
    )
    assert second_commit.status_code == 200
    second_commit_payload = second_commit.json()
    assert second_commit_payload["inserted"] == 0
    assert second_commit_payload["updated"] == 1
    assert second_commit_payload["unchanged"] == 1

    invalid_csv = "symbol,quantity,average_cost\nAAPL,10,185.50\nAAPL,8,184.00\n"
    preview_invalid = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/preview",
        files={"file": ("positions.csv", invalid_csv, "text/csv")},
    )
    assert preview_invalid.status_code == 200
    assert preview_invalid.json()["errors"][0]["issue"] == "Duplicate symbol in file"

    commit_invalid = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions/imports/commit",
        files={"file": ("positions.csv", invalid_csv, "text/csv")},
    )
    assert commit_invalid.status_code == 422
    error_payload = commit_invalid.json()
    assert error_payload["code"] == "validation_error"
    assert error_payload["details"][0]["field"] == "symbol"


def test_trading_operations_buy_and_sell_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")

    buy_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "2",
            "price": "100.00",
            "commission": "5.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert buy_response.status_code == 201
    buy_payload = buy_response.json()
    assert Decimal(buy_payload["updatedBalance"]["amount"]) == Decimal("795.00")
    assert Decimal(buy_payload["updatedPosition"]["quantity"]) == Decimal("2")
    assert Decimal(buy_payload["updatedPosition"]["averageCost"]) == Decimal("102.5")

    sell_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": "1",
            "price": "120.00",
            "commission": "5.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert sell_response.status_code == 201
    sell_payload = sell_response.json()
    assert Decimal(sell_payload["updatedBalance"]["amount"]) == Decimal("910.00")
    assert Decimal(sell_payload["updatedPosition"]["quantity"]) == Decimal("1")
    assert Decimal(sell_payload["updatedPosition"]["averageCost"]) == Decimal("102.5")

    operations_response = client.get(f"/api/v1/portfolios/{portfolio_id}/trading-operations")
    assert operations_response.status_code == 200
    assert len(operations_response.json()) == 2


def test_trading_operation_rejections(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="50.00")

    insufficient_buy = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "60.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert insufficient_buy.status_code == 400
    assert insufficient_buy.json()["code"] == "insufficient_balance"

    create_position(client, portfolio_id, symbol="AAPL", quantity="1", average_cost="10.00")
    oversell = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "SELL",
            "quantity": "2",
            "price": "12.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert oversell.status_code == 400
    assert oversell.json()["code"] == "oversell_rejected"


def test_trading_operations_respect_withdrawals_and_deposit_balances(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    deposit_balance = create_balance(client, portfolio_id, label="Broker Cash", amount="1000.00")
    withdrawal_balance = create_balance(
        client,
        portfolio_id,
        label="Cash Out",
        amount="200.00",
        operation_type="WITHDRAWAL",
    )

    insufficient_after_withdrawal = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": deposit_balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "9",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert insufficient_after_withdrawal.status_code == 400
    assert insufficient_after_withdrawal.json()["code"] == "insufficient_balance"

    invalid_withdrawal_balance = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": withdrawal_balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T15:05:00Z",
        },
    )
    assert invalid_withdrawal_balance.status_code == 400
    assert invalid_withdrawal_balance.json()["code"] == "invalid_operation_balance"


def test_trading_operations_dividend_and_split_flow(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    dividend_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "12.50",
            "commission": "0.50",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )
    assert dividend_response.status_code == 201
    dividend_payload = dividend_response.json()
    assert Decimal(dividend_payload["updatedBalance"]["amount"]) == Decimal("1012.00")
    assert Decimal(dividend_payload["updatedPosition"]["quantity"]) == Decimal("2")
    assert Decimal(dividend_payload["operation"]["dividendAmount"]) == Decimal("12.50")

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "4",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )
    assert split_response.status_code == 201
    split_payload = split_response.json()
    assert split_payload["updatedBalance"] is None
    assert split_payload["operation"]["balanceId"] is None
    assert split_payload["operation"]["balanceLabel"] == "Not Applicable"
    assert Decimal(split_payload["updatedPosition"]["quantity"]) == Decimal("8")
    assert Decimal(split_payload["updatedPosition"]["averageCost"]) == Decimal("25")
    assert Decimal(split_payload["operation"]["splitRatio"]) == Decimal("4")


def test_dividend_rejects_when_commission_would_make_balance_negative(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="0.00")
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "1.00",
            "commission": "2.00",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "insufficient_balance"


def test_dividend_requires_existing_position(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="100.00")

    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "DIVIDEND",
            "dividendAmount": "1.00",
            "commission": "0.00",
            "executedAt": "2026-03-11T10:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "no_position_for_dividend"

    balances_response = client.get(f"/api/v1/portfolios/{portfolio_id}/balances")
    assert balances_response.status_code == 200
    assert Decimal(balances_response.json()[0]["amount"]) == Decimal("100.00")

    operations_response = client.get(f"/api/v1/portfolios/{portfolio_id}/trading-operations")
    assert operations_response.status_code == 200
    assert operations_response.json() == []


def test_split_requires_existing_position(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "2",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )
    assert split_response.status_code == 400
    assert split_response.json()["code"] == "no_position_for_split"


def test_split_succeeds_without_balance(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    create_position(client, portfolio_id, symbol="AAPL", quantity="2", average_cost="100.00")

    split_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "symbol": "AAPL",
            "side": "SPLIT",
            "splitRatio": "2",
            "executedAt": "2026-03-11T11:00:00Z",
        },
    )

    assert split_response.status_code == 201
    split_payload = split_response.json()
    assert split_payload["updatedBalance"] is None
    assert split_payload["operation"]["balanceId"] is None
    assert Decimal(split_payload["updatedPosition"]["quantity"]) == Decimal("4")


def test_trade_linked_balance_cannot_change_operation_type(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    balance = create_balance(client, portfolio_id, amount="1000.00")

    trade_response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/trading-operations",
        json={
            "balanceId": balance["id"],
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": "1",
            "price": "100.00",
            "commission": "0.00",
            "executedAt": "2026-03-10T14:05:00Z",
        },
    )
    assert trade_response.status_code == 201

    update_response = client.patch(
        f"/api/v1/portfolios/{portfolio_id}/balances/{balance['id']}",
        json={"operationType": "WITHDRAWAL"},
    )

    assert update_response.status_code == 400
    assert update_response.json()["code"] == "balance_operation_type_locked"


class BrokenQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        raise QuoteProviderError(f"Unavailable for {symbol}")

    def fetch_quote(self, symbol: str) -> object:
        raise QuoteProviderError(f"Unavailable for {symbol}")


def _build_provider_quote(
    *,
    symbol: str,
    price: Decimal,
    previous_close: Decimal | None,
    currency: str,
    provider: str,
    as_of: datetime | None,
) -> ProviderQuote:
    quote = cast(ProviderQuote, object.__new__(ProviderQuote))
    quote.symbol = symbol
    quote.price = price
    quote.previous_close = previous_close
    quote.currency = currency
    quote.provider = provider
    quote.as_of = as_of
    quote.name = None
    return quote


def _build_provider_history_point(*, at: datetime, close: Decimal) -> ProviderHistoryPoint:
    point = cast(ProviderHistoryPoint, object.__new__(ProviderHistoryPoint))
    point.at = at
    point.close = close
    return point


def _build_provider_history_series(
    *,
    symbol: str,
    currency: str | None,
    provider: str,
    points: list[ProviderHistoryPoint],
) -> ProviderHistorySeries:
    series = cast(ProviderHistorySeries, object.__new__(ProviderHistorySeries))
    series.symbol = symbol
    series.currency = currency
    series.provider = provider
    series.points = points
    return series


class StableQuoteProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        if symbol.upper() == "AAPL":
            return "Apple Inc."
        return None

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        normalized_symbol = symbol.upper()
        return _build_provider_quote(
            symbol=normalized_symbol,
            price=Decimal("191.24"),
            previous_close=Decimal("189.10"),
            currency="USD",
            provider="stub_feed",
            as_of=datetime(2026, 3, 10, 13, 55, tzinfo=UTC_TZ),
        )

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        if interval != "1d" or range_value != "3mo":
            raise QuoteProviderError("Unexpected history request")

        normalized_symbol = symbol.upper()
        base_price = Decimal("100.00") if normalized_symbol == "AAPL" else Decimal("90.00")
        return _build_provider_history_series(
            symbol=normalized_symbol,
            currency="USD",
            provider="stub_feed",
            points=[
                _build_provider_history_point(
                    at=datetime(2026, 1, 5, 14, 30, tzinfo=UTC_TZ), close=base_price
                ),
                _build_provider_history_point(
                    at=datetime(2026, 2, 5, 14, 30, tzinfo=UTC_TZ),
                    close=base_price + Decimal("8.50"),
                ),
                _build_provider_history_point(
                    at=datetime(2026, 3, 5, 14, 30, tzinfo=UTC_TZ),
                    close=base_price + Decimal("12.00"),
                ),
            ],
        )


class CountingQuoteProvider(StableQuoteProvider):
    def __init__(self) -> None:
        self.quote_calls = 0

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        self.quote_calls += 1
        return super().fetch_quote(symbol)


class CountingSymbolLookupProvider:
    def __init__(self) -> None:
        self.symbol_name_calls = 0

    def fetch_symbol_name(self, symbol: str) -> str | None:
        self.symbol_name_calls += 1
        if symbol.upper() == "AAPL":
            return "Apple Inc."
        return None

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise QuoteProviderError(f"Quote lookup unavailable for {symbol}")

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        raise QuoteProviderError(f"History lookup unavailable for {symbol}")


class UnexpectedSymbolLookupProvider:
    def fetch_symbol_name(self, symbol: str) -> str | None:
        raise AssertionError(f"Symbol lookup should not run for {symbol}")

    def fetch_quote(self, symbol: str) -> ProviderQuote:
        raise QuoteProviderError(f"Quote lookup unavailable for {symbol}")

    def fetch_history(
        self, symbol: str, *, range_value: str, interval: str
    ) -> ProviderHistorySeries:
        raise QuoteProviderError(f"History lookup unavailable for {symbol}")


def test_position_symbol_lookup_returns_provider_name_and_uses_cache(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    provider = CountingSymbolLookupProvider()

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = lambda: provider

    first_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=aapl")
    second_response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=AAPL")

    application.dependency_overrides.clear()

    assert first_response.status_code == 200
    assert first_response.json() == {"symbol": "AAPL", "name": "Apple Inc."}
    assert second_response.status_code == 200
    assert second_response.json() == {"symbol": "AAPL", "name": "Apple Inc."}
    assert provider.symbol_name_calls == 1

    with session_factory() as session:
        cached = session.query(SymbolNameCache).filter_by(symbol="AAPL").one_or_none()

    assert cached is not None
    assert cached.name == "Apple Inc."


def test_position_symbol_lookup_returns_null_name_for_unresolved_symbol(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/positions/lookup?symbol=unknown")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"symbol": "UNKNOWN", "name": None}


def test_create_position_backfills_name_from_symbol_lookup_when_missing(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "quantity": "10",
            "averageCost": "185.50",
        },
    )
    application.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"
    assert response.json()["name"] == "Apple Inc."


def test_create_position_uses_manual_name_without_provider_lookup(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = UnexpectedSymbolLookupProvider
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "symbol": "AAPL",
            "name": "Manual Apple Name",
            "quantity": "10",
            "averageCost": "185.50",
        },
    )
    application.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["symbol"] == "AAPL"
    assert response.json()["name"] == "Manual Apple Name"


def test_market_data_falls_back_to_cached_quote(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    as_of = datetime(2026, 3, 10, 13, 55, tzinfo=UTC_TZ)

    with session_factory() as session:
        session.add(
            MarketQuote(
                symbol="AAPL",
                provider="yahoo_finance",
                price="191.24",
                previous_close="189.10",
                currency="USD",
                as_of=as_of,
                fetched_at=as_of,
                is_stale=False,
            )
        )
        session.commit()

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = BrokenQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["symbol"] == "AAPL"
    assert Decimal(payload["quotes"][0]["price"]) == Decimal("191.24")
    assert Decimal(payload["quotes"][0]["previousClose"]) == Decimal("189.10")
    assert payload["warnings"] == ["Using cached quote for AAPL"]


def test_market_data_recomputes_cached_quote_staleness_on_fallback(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])
    as_of = datetime.now(UTC_TZ) - timedelta(minutes=30)

    with session_factory() as session:
        cached_quote = MarketQuote(
            symbol="AAPL",
            provider="yahoo_finance",
            price="191.24",
            previous_close="189.10",
            currency="USD",
            as_of=as_of,
            fetched_at=as_of,
            is_stale=False,
        )
        session.add(cached_quote)
        session.commit()
        cached_quote_id = cached_quote.id

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = BrokenQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["isStale"] is True
    assert payload["warnings"] == ["Using cached quote for AAPL"]

    with session_factory() as session:
        refreshed_quote = session.get(MarketQuote, cached_quote_id)
        assert refreshed_quote is not None
        assert refreshed_quote.is_stale is True


def test_market_data_returns_previous_close_when_provider_supplies_it(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(f"/api/v1/portfolios/{portfolio_id}/market-data/quotes?symbols=AAPL")
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["quotes"][0]["provider"] == "stub_feed"
    assert Decimal(payload["quotes"][0]["previousClose"]) == Decimal("189.10")


def test_market_data_history_returns_multiple_series(client: TestClient) -> None:
    portfolio = create_portfolio(client)
    portfolio_id = str(portfolio["id"])

    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_quote_provider] = StableQuoteProvider
    response = client.get(
        f"/api/v1/portfolios/{portfolio_id}/market-data/history?symbols=AAPL,%5EGSPC&range=3mo"
    )
    application.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["range"] == "3mo"
    assert payload["interval"] == "1d"
    assert payload["warnings"] == []
    assert [series["symbol"] for series in payload["series"]] == ["AAPL", "^GSPC"]
    assert payload["series"][0]["points"][0]["at"] == "2026-01-05T14:30:00Z"
    assert Decimal(payload["series"][1]["points"][2]["close"]) == Decimal("102.00")


def test_validate_supported_database_engine_rejects_non_postgres() -> None:
    unsupported_engine = UnsupportedEngine("mysql")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        validate_supported_database_engine(unsupported_engine)


def test_init_db_rejects_legacy_uuid_backed_schema(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE portfolios (id VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE balances (id VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE trading_operations (
                    portfolio_id VARCHAR(32) NOT NULL,
                    balance_id VARCHAR(32),
                    balance_label VARCHAR(60) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(4) NOT NULL,
                    quantity NUMERIC(20, 8) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    commission NUMERIC(20, 4) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    id VARCHAR(32) NOT NULL PRIMARY KEY,
                    CONSTRAINT ck_trading_operations_side CHECK (side IN ('BUY', 'SELL'))
                )
                """
            )

        with pytest.raises(RuntimeError, match="Legacy UUID-backed database detected"):
            init_db(database_url)

        table_names = set(inspect(engine).get_table_names())
        assert table_names == {"balances", "portfolios", "trading_operations"}
    finally:
        engine.dispose()


def test_init_db_upgrades_legacy_balance_schema_and_drops_obsolete_tables(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE balances (
                    id INTEGER PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    label VARCHAR(60) NOT NULL,
                    amount NUMERIC(20, 4) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO balances (
                    id, portfolio_id, label, amount, currency, created_at, updated_at
                )
                VALUES (1, 1, 'Cash', 1000.00, 'USD', NOW(), NOW())
                """
            )

            for table_name in (
                "llm_configs",
                "prompt_templates",
                "user_snippets",
                "portfolio_stock_analysis_settings",
                "stock_analysis_conversations",
                "stock_analysis_runs",
                "stock_analysis_requests",
                "stock_analysis_responses",
                "stock_analysis_versions",
            ):
                connection.exec_driver_sql(f'CREATE TABLE "{table_name}" (id INTEGER PRIMARY KEY)')

        init_db(database_url)

        inspector = inspect(engine)
        balance_columns = {column["name"]: column for column in inspector.get_columns("balances")}
        assert "operation_type" in balance_columns
        assert balance_columns["operation_type"]["nullable"] is False

        with engine.connect() as connection:
            operation_type = connection.exec_driver_sql(
                "SELECT operation_type FROM balances WHERE id = 1"
            ).scalar_one()

        assert operation_type == "DEPOSIT"

        table_names = set(inspector.get_table_names())
        assert {
            "llm_configs",
            "prompt_templates",
            "user_snippets",
            "portfolio_stock_analysis_settings",
            "stock_analysis_conversations",
            "stock_analysis_runs",
            "stock_analysis_requests",
            "stock_analysis_responses",
            "stock_analysis_versions",
        }.isdisjoint(table_names)
    finally:
        engine.dispose()


def test_init_db_backfills_legacy_portfolio_slugs_with_valid_unique_values(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    base_currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO portfolios (
                    id, name, description, base_currency, created_at, updated_at
                )
                VALUES
                    (1, 'Growth Income', 'Legacy', 'USD', NOW(), NOW()),
                    (2, 'Growth-Income', 'Legacy', 'USD', NOW(), NOW()),
                    (3, '123 Allocation', 'Legacy', 'USD', NOW(), NOW()),
                    (4, '!!!', 'Legacy', 'USD', NOW(), NOW())
                """
            )

        init_db(database_url)

        portfolio_columns = {
            column["name"]: column for column in inspect(engine).get_columns("portfolios")
        }
        assert "slug" in portfolio_columns
        assert portfolio_columns["slug"]["nullable"] is False

        with engine.connect() as connection:
            slugs = (
                connection.exec_driver_sql("SELECT slug FROM portfolios ORDER BY id")
                .scalars()
                .all()
            )

        assert slugs == [
            "growth_income",
            "growth_income_2",
            "portfolio_123_allocation",
            "portfolio",
        ]
        assert len(set(slugs)) == len(slugs)
    finally:
        engine.dispose()


def test_init_db_adds_market_quote_name_column_for_legacy_schema(
    database_url: str,
) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE market_quotes (
                    id INTEGER PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL,
                    provider VARCHAR(50) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    previous_close NUMERIC(20, 8),
                    currency VARCHAR(3) NOT NULL,
                    as_of TIMESTAMP WITH TIME ZONE,
                    fetched_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    is_stale BOOLEAN NOT NULL
                )
                """
            )

        init_db(database_url)

        market_quote_columns = {
            column["name"]: column for column in inspect(engine).get_columns("market_quotes")
        }
        assert "name" in market_quote_columns
        assert market_quote_columns["name"]["nullable"] is True
    finally:
        engine.dispose()


def test_init_db_creates_symbol_name_cache_as_unlogged_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            relpersistence = connection.exec_driver_sql(
                "SELECT relpersistence FROM pg_class WHERE relname = 'symbol_name_cache'"
            ).scalar_one()

        assert relpersistence == "u"
    finally:
        engine.dispose()


def test_report_compile_crud_and_download(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Retirement", slug="retirement")
    create_balance(client, str(portfolio["id"]), label="Cash", amount="1500.00")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    template = create_template(
        client,
        name="Monthly Report",
        content=(
            "# Report\n\n"
            "Slug: {{portfolios.retirement.slug}}\n"
            "Positions:\n{{portfolios.retirement.positions}}"
        ),
    )

    compile_response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert compile_response.status_code == 201
    report = compile_response.json()
    assert report["name"].startswith("monthly_report_")
    assert report["slug"].startswith("monthly_report_")
    assert report["source"] == "compiled"
    assert "metadata" in report
    assert "Slug: retirement" in report["content"]
    assert "AAPL" in report["content"]
    assert "createdAt" in report
    assert "updatedAt" in report

    list_response = client.get("/api/v1/reports")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == report["id"]

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == report["name"]
    assert get_response.json()["content"] == report["content"]

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Edited Report\n\nManual edit."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Edited Report\n\nManual edit."
    assert update_response.json()["name"] == report["name"]

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert "text/markdown" in download_response.headers["content-type"]
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Edited Report\n\nManual edit."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_report_compile_nonexistent_template(client: TestClient) -> None:
    response = client.post("/api/v1/reports/compile/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_report_name_generation_and_uniqueness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_now = datetime(2026, 3, 18, 10, 56, 51, tzinfo=UTC_TZ)
    monkeypatch.setattr("app.services.report_service.utcnow", lambda: fixed_now)

    template = create_template(
        client,
        name="Q1 Summary",
        content="# Q1",
    )

    first = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert first.status_code == 201
    first_name = first.json()["name"]
    first_slug = first.json()["slug"]
    assert first_name.startswith("q1_summary_")
    assert first_slug == first_name

    second = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert second.status_code == 201
    second_name = second.json()["name"]
    second_slug = second.json()["slug"]
    assert second_name != first_name
    assert second_name.startswith("q1_summary_")
    assert second_name.endswith("_2")
    assert second_slug == second_name


def test_report_name_normalization(client: TestClient) -> None:
    template = create_template(
        client,
        name="My Portfolio — March",
        content="# March",
    )

    response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert response.status_code == 201
    name = response.json()["name"]
    assert name.startswith("my_portfolio_march_")
    assert "—" not in name
    assert " " not in name


def test_report_update_name_immutability(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Updated", "name": "new_name"},
    )
    assert response.status_code == 422


def test_report_update_validation(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    empty_payload = client.patch(f"/api/v1/reports/{report['slug']}", json={})
    assert empty_payload.status_code == 422

    whitespace_content = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "   "},
    )
    assert whitespace_content.status_code == 422


def test_report_404s(client: TestClient) -> None:
    assert client.get("/api/v1/reports/99999").status_code == 404
    assert client.patch("/api/v1/reports/99999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/v1/reports/99999").status_code == 404
    assert client.get("/api/v1/reports/99999/download").status_code == 404


def test_report_name_timestamp_format(client: TestClient) -> None:
    import re

    template = create_template(client, name="Timestamp Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    name = report["name"]

    pattern = r"^timestamp_test_\d{8}_\d{6}$"
    assert re.match(pattern, name), f"Name '{name}' does not match expected format"


def test_report_name_max_length_truncation(client: TestClient) -> None:
    long_name = "A" * 100
    template = create_template(client, name=long_name, content="# Long")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    assert len(report["name"]) <= 200


def test_report_upload_crud_and_download(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Quarterly Update.md",
                b"# Uploaded Report\n\nBody text.",
                "text/markdown",
            )
        },
        data={
            "slug": "quarterly_update",
            "author": "Analyst",
            "description": "Uploaded from disk",
            "tags": "quarterly, finance",
        },
    )
    assert upload_response.status_code == 201
    report = upload_response.json()
    assert report["name"] == "Quarterly Update"
    assert report["slug"] == "quarterly_update"
    assert report["source"] == "uploaded"
    assert report["metadata"] == {
        "author": "Analyst",
        "description": "Uploaded from disk",
        "tags": ["quarterly", "finance"],
    }

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == "# Uploaded Report\n\nBody text."

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Uploaded Report\n\nEdited body text."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Uploaded Report\n\nEdited body text."

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Uploaded Report\n\nEdited body text."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_code"),
    [
        ("notes.txt", b"# Not markdown", "text/plain", "invalid_file_type"),
        ("broken.md", b"\xff\xfe\x00", "application/octet-stream", "invalid_file_encoding"),
    ],
)
def test_report_upload_validation(
    client: TestClient,
    filename: str,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    response = client.post(
        "/api/v1/reports/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json()["code"] == expected_code


def test_report_compile_accepts_extensible_metadata(client: TestClient) -> None:
    template = create_template(client, name="Weekly Review", content="# Weekly")

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "author": " Analyst ",
                "tags": [" weekly_review ", "reflection"],
                "analysis": {
                    "ticker": "aapl",
                    "portfolioSlug": "core_us",
                    "customKey": "custom-value",
                },
                "customBlock": {"foo": "bar"},
            }
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["source"] == "compiled"
    assert report["metadata"]["author"] == "Analyst"
    assert report["metadata"]["tags"] == ["weekly_review", "reflection"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["portfolioSlug"] == "core_us"
    assert report["metadata"]["analysis"]["customKey"] == "custom-value"
    assert report["metadata"]["customBlock"] == {"foo": "bar"}


def test_report_compile_accepts_runtime_inputs(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Runtime Compile", slug="runtime_compile")
    create_position(
        client, str(portfolio["id"]), symbol="MSFT", quantity="7", average_cost="398.00"
    )

    client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Prior Analysis",
            "content": "MSFT prior report body",
            "metadata": {
                "tags": ["msft_loop"],
                "analysis": {"ticker": "MSFT"},
            },
        },
    )

    template = create_template(
        client,
        name="Runtime Report Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Portfolio: {{portfolios.by_slug(inputs.portfolio_slug).name}}\n"
            "Quantity: {{portfolios.by_slug(inputs.portfolio_slug).positions."
            "by_symbol(inputs.ticker).quantity}}\n"
            "Prior: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "inputs": {
                "ticker": "MSFT",
                "portfolio_slug": "runtime_compile",
            },
            "metadata": {
                "tags": ["runtime_compile"],
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["content"] == (
        "Ticker: MSFT\n"
        "Portfolio: Runtime Compile\n"
        "Quantity: 7.00000000\n"
        "Prior: MSFT prior report body"
    )
    assert report["metadata"]["tags"] == ["runtime_compile"]


def test_report_create_external_json(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Weekly Reflection",
            "content": "# AAPL\n\nReview body.",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "aapl",
                    "reviewType": "weekly_review",
                },
                "customFlag": True,
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["name"] == "AAPL Weekly Reflection"
    assert report["slug"] == "aapl_weekly_reflection"
    assert report["source"] == "external"
    assert report["metadata"]["tags"] == ["weekly_review"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["reviewType"] == "weekly_review"
    assert report["metadata"]["customFlag"] is True

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["source"] == "external"


def test_report_external_non_memory_update_and_delete_remains_allowed(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL External Follow Up",
            "content": "# AAPL\n\nOriginal body.",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "versionGroup": "weekly_review/v1",
                },
            },
        },
    )
    assert create_response.status_code == 201
    report = create_response.json()

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# AAPL\n\nEdited external body."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["source"] == "external"
    assert update_response.json()["content"] == "# AAPL\n\nEdited external body."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/reports/{report['slug']}").status_code == 404


def test_report_create_external_slug_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/reports",
        json={
            "name": "External One",
            "slug": "external_one",
            "content": "# One",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/reports",
        json={
            "name": "External Two",
            "slug": "external_one",
            "content": "# Two",
        },
    )
    assert second.status_code == 409
    assert second.json()["code"] == "slug_conflict"


def test_report_list_filters_and_pagination(client: TestClient) -> None:
    template = create_template(client, name="AAPL Weekly Template", content="# Weekly")

    compiled = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review", "reflection"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Monthly Reflection",
            "content": "# AAPL Monthly",
            "metadata": {
                "tags": ["monthly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "monthly_review",
                    "portfolioSlug": "core_us",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Weekly Reflection",
            "content": "# MSFT Weekly",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "growth",
                },
            },
        },
    ).json()

    uploaded = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nArchive body.",
                "text/markdown",
            )
        },
        data={
            "slug": "uploaded_note",
            "tags": "archive",
        },
    ).json()

    all_reports = client.get("/api/v1/reports")
    assert all_reports.status_code == 200
    assert [report["id"] for report in all_reports.json()] == [
        uploaded["id"],
        external_msft["id"],
        external_aapl["id"],
        compiled["id"],
    ]

    by_ticker = client.get("/api/v1/reports", params={"ticker": "aapl"})
    assert by_ticker.status_code == 200
    assert [report["id"] for report in by_ticker.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_tag = client.get("/api/v1/reports", params={"tag": "weekly_review"})
    assert by_tag.status_code == 200
    assert [report["id"] for report in by_tag.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_review_type = client.get("/api/v1/reports", params={"reviewType": "weekly_review"})
    assert by_review_type.status_code == 200
    assert [report["id"] for report in by_review_type.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_portfolio = client.get("/api/v1/reports", params={"portfolioSlug": "core_us"})
    assert by_portfolio.status_code == 200
    assert [report["id"] for report in by_portfolio.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_source = client.get("/api/v1/reports", params={"source": "external"})
    assert by_source.status_code == 200
    assert [report["id"] for report in by_source.json()] == [
        external_msft["id"],
        external_aapl["id"],
    ]

    combined = client.get(
        "/api/v1/reports",
        params={
            "ticker": "AAPL",
            "reviewType": "weekly_review",
            "portfolioSlug": "core_us",
        },
    )
    assert combined.status_code == 200
    assert [report["id"] for report in combined.json()] == [compiled["id"]]

    paginated = client.get(
        "/api/v1/reports",
        params={"source": "external", "limit": 1, "offset": 1},
    )
    assert paginated.status_code == 200
    assert [report["id"] for report in paginated.json()] == [external_aapl["id"]]


def test_report_source_filter_accepts_agent(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    external_response = client.post(
        "/api/v1/reports",
        json={
            "name": "True External Filter Companion",
            "content": "# External",
        },
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    assert external_report["source"] == "external"

    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Memory Report",
        slug="agent_memory_report",
        source="agent",
        content="# Agent Memory",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": 101,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
            "analysis": {
                "reviewType": "agent_memory",
                "versionGroup": "agent_memory/v1",
                "runId": 101,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
        },
    )

    response = client.get("/api/v1/reports", params={"source": "agent"})

    assert response.status_code == 200
    reports = response.json()
    assert [report["id"] for report in reports] == [agent_report_id]
    assert external_report["id"] not in [report["id"] for report in reports]
    assert reports[0]["source"] == "agent"
    assert reports[0]["metadata"]["createdBy"]["agentKey"] == "analyst"


def test_report_source_filter_external_excludes_agent_reports(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    external_response = client.post(
        "/api/v1/reports",
        json={
            "name": "True External Report",
            "content": "# External",
        },
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Memory External Exclusion",
        slug="agent_memory_external_exclusion",
        source="agent",
        content="# Agent Memory",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": 202,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
            "analysis": {
                "reviewType": "agent_memory",
                "versionGroup": "agent_memory/v1",
                "runId": 202,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
        },
    )

    agent_response = client.get("/api/v1/reports", params={"source": "agent"})
    response = client.get("/api/v1/reports", params={"source": "external"})

    assert agent_response.status_code == 200
    agent_report_ids = [report["id"] for report in agent_response.json()]
    assert agent_report_ids == [agent_report_id]
    assert external_report["id"] not in agent_report_ids
    assert agent_response.json()[0]["metadata"]["createdBy"]["runId"] == 202

    assert response.status_code == 200
    report_ids = [report["id"] for report in response.json()]
    assert report_ids == [external_report["id"]]
    assert agent_report_id not in report_ids
    assert response.json()[0]["source"] == "external"


def test_public_report_create_rejects_agent_created_by_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_by = {
        "type": "agent",
        "runId": 303,
        "agentKey": "spoofed-agent",
        "agentVersion": 1,
    }
    expected_message = (
        "Report createdBy provenance is server-owned and cannot be supplied for non-agent reports."
    )

    create_response = client.post(
        "/api/v1/reports",
        json={
            "name": "Spoofed External Report",
            "content": "# Spoofed",
            "metadata": {"createdBy": created_by},
        },
    )

    assert create_response.status_code == 400
    assert create_response.json()["code"] == "invalid_report_provenance"
    assert create_response.json()["message"] == expected_message

    template = create_template(client, name="Spoofed Compile", content="# Compile")
    compile_response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={"metadata": {"createdBy": created_by}},
    )

    assert compile_response.status_code == 400
    assert compile_response.json()["code"] == "invalid_report_provenance"
    assert compile_response.json()["message"] == expected_message

    with session_factory() as session:
        service = ReportService(session)
        with pytest.raises(ApiError) as upload_error:
            service.create_from_upload(
                content="# Uploaded Spoof",
                slug="uploaded_spoof",
                name="Uploaded Spoof",
                metadata={"createdBy": created_by},
            )
        with pytest.raises(ApiError) as external_error:
            service.create_external_report(
                content="# Snake Case Spoof",
                name="Snake Case Spoof",
                metadata={"created_by": created_by},
            )

    for error in (upload_error.value, external_error.value):
        assert error.status_code == 400
        assert error.code == "invalid_report_provenance"
        assert error.message == expected_message


def test_report_placeholder_all_paths(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    source_template = create_template(
        client,
        name="Source",
        content="Name: {{portfolios.growth.name}}",
    )
    report_response = client.post(f"/api/v1/reports/compile/{source_template['id']}")
    assert report_response.status_code == 201
    report = report_response.json()
    report_name = report["name"]

    meta_template = create_template(
        client,
        name="Report Meta Test",
        content=(
            "All: {{reports}}\n"
            f"Single: {{{{reports.{report_name}}}}}\n"
            f"Content: {{{{reports.{report_name}.content}}}}\n"
            f"NameField: {{{{reports.{report_name}.name}}}}\n"
            f"Created: {{{{reports.{report_name}.created_at}}}}\n"
            "Unknown: {{reports.nonexistent_report}}\n"
            f"BadField: {{{{reports.{report_name}.unknown_field}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{meta_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled.startswith("All: - **")
    assert f"**{report_name}**" in compiled

    single_line = [line for line in compiled.split("\n") if line.startswith("Single: ")][0]
    assert single_line.startswith(f"Single: **{report_name}**")
    assert "(" in single_line and "Z)" in single_line

    assert "Content: Name: Growth" in compiled

    assert f"NameField: {report_name}" in compiled

    created_line = [line for line in compiled.split("\n") if line.startswith("Created: ")][0]
    created_value = created_line.replace("Created: ", "")
    assert created_value.endswith("Z")
    assert "T" in created_value

    assert "[Unknown report: nonexistent_report]" in compiled
    assert "[Unknown report field: unknown_field]" in compiled


def test_report_placeholder_recompilation(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Recomp", slug="recomp")
    create_position(
        client, str(portfolio["id"]), symbol="TSLA", quantity="5", average_cost="200.00"
    )

    source_template = create_template(
        client,
        name="Recomp Source",
        content="Original: {{portfolios.recomp.name}}",
    )
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={
            "content": (
                "Name: {{portfolios.recomp.name}}\nPositions: {{portfolios.recomp.positions}}"
            )
        },
    )

    embed_template = create_template(
        client,
        name="Embed Test",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Name: Recomp" in compiled
    assert "TSLA" in compiled


def test_report_placeholder_cycle_detection_self_reference(
    client: TestClient,
) -> None:
    source_template = create_template(client, name="Self Ref", content="# Self")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": f"{{{{reports.{report_name}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Self Ref Embed",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report_name}]" in compiled


def test_report_placeholder_cycle_detection_indirect(
    client: TestClient,
) -> None:
    tmpl_a = create_template(client, name="Cycle A", content="# A")
    tmpl_b = create_template(client, name="Cycle B", content="# B")
    report_a = client.post(f"/api/v1/reports/compile/{tmpl_a['id']}").json()
    report_b = client.post(f"/api/v1/reports/compile/{tmpl_b['id']}").json()
    name_a = report_a["name"]
    name_b = report_b["name"]

    client.patch(
        f"/api/v1/reports/{report_a['slug']}",
        json={"content": f"A includes B: {{{{reports.{name_b}.content}}}}"},
    )
    client.patch(
        f"/api/v1/reports/{report_b['slug']}",
        json={"content": f"B includes A: {{{{reports.{name_a}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Indirect Cycle",
        content=f"{{{{reports.{name_a}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert (
        f"[Circular report reference: {name_a}]" in compiled
        or f"[Circular report reference: {name_b}]" in compiled
    )


def test_placeholder_tree_includes_reports(client: TestClient) -> None:
    source_template = create_template(client, name="Tree Test", content="# Tree")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()

    tree_response = client.get("/api/v1/templates/placeholders")
    assert tree_response.status_code == 200
    tree = tree_response.json()

    assert "reports" in tree
    report_names = [r["name"] for r in tree["reports"]]
    assert report["name"] in report_names
    assert "createdAt" in tree["reports"][0]


def test_report_placeholder_dynamic_selectors(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Growth", slug="growth")
    create_position(
        client, str(portfolio["id"]), symbol="AAPL", quantity="10", average_cost="185.50"
    )

    source_template = create_template(client, name="Latest Report", content="Compiled AAPL")
    compiled_aapl = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Dynamic Latest",
            "content": "Dynamic AAPL: {{portfolios.growth.name}}",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "core_us",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Dynamic Latest",
            "content": "MSFT body",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                    "portfolioSlug": "growth",
                },
            },
        },
    ).json()

    selector_template = create_template(
        client,
        name="Dynamic Selector Test",
        content=(
            "LatestMeta: {{reports.latest}}\n"
            "LatestName: {{reports.latest.name}}\n"
            'TickerLatestName: {{reports.latest("AAPL").name}}\n'
            'TickerLatestContent: {{reports.latest("AAPL").content}}\n'
            "IndexZeroName: {{reports[0].name}}\n"
            'TagLatestName: {{reports.by_tag("weekly_review").latest.name}}\n'
            'TagLatestContent: {{reports.by_tag("weekly_review").latest.content}}\n'
            'NoMatchInline: before{{reports.latest("NVDA").name}}after\n'
            "NoMatchIndex: before{{reports[99].content}}after\n"
            'InvalidSelector: {{reports.by_tag("weekly_review")}}\n'
            f"ExactNameCompatibility: {{{{reports.{compiled_aapl['name']}.name}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    latest_meta_line = [line for line in compiled.split("\n") if line.startswith("LatestMeta: ")][0]
    assert latest_meta_line.startswith(f"LatestMeta: **{external_msft['name']}**")
    assert f"LatestName: {external_msft['name']}" in compiled
    assert f"TickerLatestName: {external_aapl['name']}" in compiled
    assert "TickerLatestContent: Dynamic AAPL: Growth" in compiled
    assert f"IndexZeroName: {external_msft['name']}" in compiled
    assert f"TagLatestName: {external_msft['name']}" in compiled
    assert "TagLatestContent: MSFT body" in compiled
    assert "NoMatchInline: beforeafter" in compiled
    assert "NoMatchIndex: beforeafter" in compiled
    assert 'InvalidSelector: [Invalid report selector: reports.by_tag("weekly_review")]' in compiled
    assert f"ExactNameCompatibility: {compiled_aapl['name']}" in compiled


def test_report_placeholder_dynamic_selector_cycle_detection(client: TestClient) -> None:
    source_template = create_template(client, name="Cycle Selector", content="# Start")
    report = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": '{{reports.latest("AAPL").content}}'},
    )

    embed_template = create_template(
        client,
        name="Dynamic Cycle Embed",
        content='{{reports.latest("AAPL").content}}',
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report['name']}]" in compiled


def test_report_filters_and_dynamic_selectors_ignore_reports_without_analysis_metadata(
    client: TestClient,
) -> None:
    uploaded = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nLegacy body.",
                "text/markdown",
            )
        },
        data={"slug": "uploaded_note"},
    ).json()

    external = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Metadata Report",
            "content": "AAPL body",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                }
            },
        },
    ).json()

    filtered = client.get("/api/v1/reports", params={"ticker": "AAPL"})
    assert filtered.status_code == 200
    assert [report["id"] for report in filtered.json()] == [external["id"]]

    selector_template = create_template(
        client,
        name="Missing Analysis Selector",
        content=(
            'TickerLatest: {{reports.latest("AAPL").name}}\n'
            'NoTickerMatch: before{{reports.latest("MSFT").content}}after'
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert f"TickerLatest: {external['name']}" in compiled
    assert f"TickerLatest: {uploaded['name']}" not in compiled
    assert "NoTickerMatch: beforeafter" in compiled


def test_init_db_upgrades_legacy_report_schema(database_url: str) -> None:
    """Verify that upgrade_legacy_schema adds slug, source, and metadata to a
    pre-existing reports table that only has the original (name, content) columns."""
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE reports (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO reports (name, content)
                VALUES ('legacy_report_20260101_120000', '# Legacy')
                """
            )

        init_db(database_url)

        inspector = inspect(engine)
        report_columns = {column["name"]: column for column in inspector.get_columns("reports")}

        assert "slug" in report_columns
        assert report_columns["slug"]["nullable"] is False

        assert "source" in report_columns
        assert report_columns["source"]["nullable"] is False

        assert "metadata" in report_columns

        with engine.connect() as connection:
            row = connection.exec_driver_sql(
                "SELECT slug, source, metadata FROM reports"
                " WHERE name = 'legacy_report_20260101_120000'"
            ).one()

        assert row[0] == "legacy_report_20260101_120000"  # slug backfilled from name
        assert row[1] == "compiled"  # source defaults to 'compiled'
        assert row[2] == {}  # metadata defaults to empty object
    finally:
        engine.dispose()


def test_model_connection_round_trips_connection_kind(client: TestClient) -> None:
    payload = {**_model_connection_create_payload(), "connectionKind": "deterministic_smoke"}

    create_response = client.post("/api/model-connections", json=payload)
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    assert create_body["connectionKind"] == "deterministic_smoke"
    connection_id = cast(int, create_body["id"])

    patch_response = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"connectionKind": "provider"},
    )
    assert patch_response.status_code == 200, patch_response.json()
    patch_body = cast(dict[str, object], patch_response.json())
    assert patch_body["connectionKind"] == "provider"

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["connectionKind"] == "provider"


def test_model_connection_connection_test_uses_provider_openai_behavior(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 0, tzinfo=UTC_TZ)

    class _RecordingOpenAIResponse:
        _request_id = "req-provider-connection-test"

    class _RecordingOpenAIClient:
        init_calls: list[dict[str, object]] = []
        response_calls: list[dict[str, object]] = []

        class _Responses:
            def __init__(self, client: _RecordingOpenAIClient) -> None:
                self._client = client

            def create(self, **kwargs: object) -> _RecordingOpenAIResponse:
                self._client.response_calls.append(dict(kwargs))
                return _RecordingOpenAIResponse()

        def __init__(self, **kwargs: object) -> None:
            self.init_calls.append(dict(kwargs))
            self.responses = self._Responses(self)

        def __enter__(self) -> _RecordingOpenAIClient:
            return self

        def __exit__(self, exc_type: object, exc_value: object, exc_traceback: object) -> bool:
            return False

    monkeypatch.setattr("app.services.model_connection_service.OpenAI", _RecordingOpenAIClient)
    monkeypatch.setattr("app.services.model_connection_service.utcnow", lambda: fixed_now)

    create_response = client.post("/api/model-connections", json=_model_connection_create_payload())
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    connection_id = cast(int, create_body["id"])

    test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert test_response.status_code == 200, test_response.json()
    test_body = cast(dict[str, object], test_response.json())
    assert test_body["modelConnectionId"] == connection_id
    assert test_body["ok"] is True
    assert (
        test_body["message"] == "Connection test succeeded (request req-provider-connection-test)."
    )
    assert (
        datetime.fromisoformat(cast(str, test_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
    assert _RecordingOpenAIClient.init_calls == [
        {
            "api_key": "sk-test-model-connection",
            "base_url": "https://api.openai.com/v1",
            "timeout": 60.0,
            "max_retries": 0,
        }
    ]
    assert _RecordingOpenAIClient.response_calls == [
        {
            "model": "gpt-5.5-mini",
            "instructions": "Reply with the single word OK.",
            "input": "Connection test.",
            "reasoning": {"effort": "medium"},
        }
    ]

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["lastTestOk"] is True
    assert (
        get_body["lastTestMessage"]
        == "Connection test succeeded (request req-provider-connection-test)."
    )
    assert (
        datetime.fromisoformat(cast(str, get_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )


def test_model_connection_connection_test_uses_smoke_kind_without_openai(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 5, tzinfo=UTC_TZ)

    class _UnexpectedOpenAIClient:
        def __init__(self, **kwargs: object) -> None:
            raise AssertionError("OpenAI should not be used for deterministic_smoke connections")

    monkeypatch.setattr("app.services.model_connection_service.OpenAI", _UnexpectedOpenAIClient)
    monkeypatch.setattr("app.services.model_connection_service.utcnow", lambda: fixed_now)

    payload = {
        **_model_connection_create_payload(),
        "connectionKind": "deterministic_smoke",
        "baseUrl": "https://smoke.invalid/v1",
        "modelId": "smoke-check",
        "apiStyle": "chat_completions",
    }
    payload.pop("apiKey")

    create_response = client.post("/api/model-connections", json=payload)
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    connection_id = cast(int, create_body["id"])

    test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert test_response.status_code == 200, test_response.json()
    test_body = cast(dict[str, object], test_response.json())
    assert test_body["modelConnectionId"] == connection_id
    assert test_body["ok"] is True
    assert test_body["message"] == "Deterministic smoke test succeeded."
    assert (
        datetime.fromisoformat(cast(str, test_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["lastTestOk"] is True
    assert get_body["lastTestMessage"] == "Deterministic smoke test succeeded."
    assert (
        datetime.fromisoformat(cast(str, get_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
