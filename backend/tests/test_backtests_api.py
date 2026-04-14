# pyright: reportMissingImports=false

from __future__ import annotations

import datetime as dt
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_engine, get_session_factory, init_db
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.models.trading_operation import TradingOperation
from app.schemas.backtest import BacktestRead
from app.services.runtime_control_service import RuntimeControlService

SUPPORTED_BACKTEST_PATTERN_KEYS = (
    "seeded_internal_backtest_v1",
    "analyst_reviewer_v1",
    "seeded_internal_backtest_tool_enabled_v1",
    "analyst_reviewer_tool_enabled_v1",
)

SUPPORTED_NON_DEFAULT_BACKTEST_PATTERN_KEYS = SUPPORTED_BACKTEST_PATTERN_KEYS[1:]


def create_portfolio(
    client: TestClient,
    *,
    name: str = "Core Portfolio",
    slug: str = "core_portfolio",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/portfolios",
        json={
            "name": name,
            "slug": slug,
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
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/balances",
        json={"label": label, "amount": amount, "operationType": operation_type},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def create_template(
    client: TestClient,
    *,
    name: str = "Backtest Template",
    content: str = "# Template",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def build_backtest_payload(
    portfolio_id: int,
    *,
    template_id: int | None,
    create_template: bool = False,
    template_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Daily Backtest",
        "portfolioId": portfolio_id,
        "templateId": template_id,
        "createTemplate": create_template,
        "templateName": template_name,
        "launchMode": "internal",
        "frequency": "DAILY",
        "startDate": "2024-01-02",
        "endDate": "2024-03-29",
        "webhookUrl": "http://localhost:5678/webhook/test",
        "webhookTimeout": 600,
        "priceMode": "CLOSING_PRICE",
        "commissionMode": "ZERO",
        "commissionValue": "0",
        "benchmarkSymbols": ["^GSPC"],
    }
    if overrides:
        payload.update(overrides)
    return payload


@pytest.fixture()
def submitted_backtests(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    submitted: list[int] = []

    monkeypatch.setattr(
        "app.services.backtest_service.BacktestService.run_backtest",
        lambda self, backtest_id: submitted.append(backtest_id),
    )
    return submitted


def test_init_db_creates_backtests_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("backtests")}
        assert {
            "portfolio_id",
            "deposit_balance_id",
            "launch_mode",
            "workflow_spec_key",
            "workflow_spec_version",
            "execution_owner",
            "current_run_id",
            "last_completed_run_id",
            "launch_mode_classified_at",
            "launch_mode_classified_by",
            "launch_mode_classification_note",
            "status",
            "frequency",
            "orchestration_pattern_key",
            "benchmark_symbols",
            "recent_activity",
            "results",
        } <= columns
    finally:
        engine.dispose()


def test_init_db_upgrades_backtests_with_orchestration_pattern_key(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE portfolios (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    base_currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE balances (
                    id SERIAL PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    label VARCHAR(60) NOT NULL,
                    operation_type VARCHAR NOT NULL,
                    amount NUMERIC(20, 4) NOT NULL,
                    currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE text_templates (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE backtests (
                    id SERIAL PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    deposit_balance_id INTEGER NOT NULL REFERENCES balances(id) ON DELETE RESTRICT,
                    name VARCHAR(200) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    frequency VARCHAR(10) NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NOT NULL,
                    current_cycle_date DATE NULL,
                    total_cycles INTEGER NOT NULL DEFAULT 0,
                    completed_cycles INTEGER NOT NULL DEFAULT 0,
                    template_id INTEGER NOT NULL REFERENCES text_templates(id) ON DELETE RESTRICT,
                    webhook_url VARCHAR(1000) NOT NULL,
                    webhook_timeout INTEGER NOT NULL DEFAULT 600,
                    current_cycle_status VARCHAR(30) NULL,
                    price_mode VARCHAR(20) NOT NULL,
                    commission_mode VARCHAR(20) NOT NULL,
                    commission_value NUMERIC(18, 8) NOT NULL DEFAULT 0,
                    benchmark_symbols JSONB NOT NULL DEFAULT '[]',
                    recent_activity JSONB NULL,
                    results JSONB NULL,
                    error_message TEXT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO portfolios (name, slug, description, base_currency)
                VALUES ('Legacy Portfolio', 'legacy_portfolio', NULL, 'USD')
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO balances (portfolio_id, label, operation_type, amount, currency)
                VALUES (1, 'Cash', 'DEPOSIT', 1000.00, 'USD')
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO text_templates (name, content)
                VALUES ('Legacy Template', '# Template')
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO backtests (
                    portfolio_id,
                    deposit_balance_id,
                    name,
                    status,
                    frequency,
                    start_date,
                    end_date,
                    template_id,
                    webhook_url,
                    webhook_timeout,
                    price_mode,
                    commission_mode,
                    commission_value,
                    benchmark_symbols
                ) VALUES (
                    1,
                    1,
                    'Legacy Backtest',
                    'PENDING',
                    'DAILY',
                    DATE '2024-01-02',
                    DATE '2024-01-31',
                    1,
                    'http://localhost:5678/webhook/test',
                    600,
                    'CLOSING_PRICE',
                    'ZERO',
                    0,
                    '["^GSPC"]'::jsonb
                )
                """
            )

        init_db(database_url)

        columns = {column["name"] for column in inspect(engine).get_columns("backtests")}
        assert "orchestration_pattern_key" in columns
        assert "launch_mode" in columns
        assert "workflow_spec_key" in columns
        assert "workflow_spec_version" in columns
        assert "execution_owner" in columns
        assert "current_run_id" in columns
        assert "last_completed_run_id" in columns
        assert "launch_mode_classified_at" in columns
        assert "launch_mode_classified_by" in columns
        assert "launch_mode_classification_note" in columns

        with engine.begin() as connection:
            row = connection.exec_driver_sql(
                "SELECT orchestration_pattern_key, launch_mode, workflow_spec_key, "
                "workflow_spec_version, execution_owner, current_run_id, "
                "last_completed_run_id, launch_mode_classified_at, "
                "launch_mode_classified_by, launch_mode_classification_note "
                "FROM backtests WHERE id = 1"
            ).one()
        assert row == (
            "seeded_internal_backtest_v1",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    finally:
        engine.dispose()


def test_init_db_upgrades_trading_operations_with_backtest_id(database_url: str) -> None:
    engine = create_engine(database_url, future=True)

    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE portfolios (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    slug VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    base_currency VARCHAR(3) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE trading_operations (
                    id SERIAL PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                    balance_id INTEGER NULL,
                    balance_label VARCHAR(60) NOT NULL,
                    symbol VARCHAR(32) NOT NULL,
                    side VARCHAR(10) NOT NULL,
                    quantity NUMERIC(20, 8),
                    price NUMERIC(20, 8),
                    commission NUMERIC(20, 4) NOT NULL DEFAULT 0,
                    currency VARCHAR(3) NOT NULL,
                    dividend_amount NUMERIC(20, 4),
                    split_ratio NUMERIC(10, 6),
                    executed_at TIMESTAMPTZ NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

        init_db(database_url)
        columns = {column["name"] for column in inspect(engine).get_columns("trading_operations")}
        assert "backtest_id" in columns
    finally:
        engine.dispose()


def test_backtest_repository_lists_newest_first(session_factory: sessionmaker[Session]) -> None:
    from app.models.backtest import Backtest
    from app.repositories.backtest import BacktestRepository

    with session_factory() as session:
        portfolio = Portfolio(
            name="Repository", slug="repository", description=None, base_currency="USD"
        )
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Cash",
            operation_type="DEPOSIT",
            amount=Decimal("1000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Repository Template", content="# Template")
        session.add_all([balance, template])
        session.flush()

        repo = BacktestRepository(session)
        first = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="First",
            status="PENDING",
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=21,
            completed_cycles=0,
            template_id=template.id,
            webhook_url="http://localhost:5678/webhook/test",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        second = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Second",
            status="RUNNING",
            frequency="WEEKLY",
            start_date=date(2024, 2, 1),
            end_date=date(2024, 3, 29),
            total_cycles=9,
            completed_cycles=1,
            template_id=template.id,
            webhook_url="http://localhost:5678/webhook/test",
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
        )
        session.add_all([first, second])
        session.commit()

        ordered = repo.list_all()
        assert ordered[0].id == second.id


def test_backtest_routes_support_list_get_cancel_and_delete(
    client: TestClient, submitted_backtests: list[int], session_factory: sessionmaker[Session]
) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client)

    create_response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(portfolio["id"], template_id=template["id"]),
    )
    assert create_response.status_code == 201, create_response.json()
    created = create_response.json()
    assert submitted_backtests == [created["id"]]

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]
    assert list_response.json()[0]["portfolioName"] == portfolio["name"]
    assert list_response.json()[0]["orchestrationPatternKey"] == "seeded_internal_backtest_v1"

    get_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]
    assert get_response.json()["webhookUrl"] == "http://localhost:5678/webhook/test"
    assert get_response.json()["webhookTimeout"] == 600
    assert get_response.json()["portfolioName"] == portfolio["name"]
    assert get_response.json()["orchestrationPatternKey"] == "seeded_internal_backtest_v1"

    cancel_response = client.post(f"/api/v1/backtests/{created['id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"

    delete_response = client.delete(f"/api/v1/backtests/{created['id']}")
    assert delete_response.status_code == 204

    with session_factory() as session:
        from app.models.backtest import Backtest

        assert session.get(Backtest, created["id"]) is None


def test_create_backtest_returns_pending_and_submits_engine(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    portfolio = create_portfolio(client)
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Launch Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(portfolio["id"], template_id=template["id"]),
    )
    assert response.status_code == 201, response.json()
    assert response.json()["status"] == "PENDING"
    assert response.json()["orchestrationPatternKey"] == "seeded_internal_backtest_v1"
    assert submitted_backtests == [response.json()["id"]]

    with session_factory() as session:
        backtest = session.get(Backtest, response.json()["id"])
        assert backtest is not None
        assert backtest.launch_mode == "internal"
        assert backtest.workflow_spec_key == "seeded_internal_backtest_v1"
        assert backtest.workflow_spec_version == 1
        assert backtest.execution_owner == "legacy_path"


def test_create_backtest_rejects_unknown_orchestration_pattern_key(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Unknown Pattern", slug="unknown_pattern")
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Unknown Pattern Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"orchestrationPatternKey": "seeded_internal_backtest_tool_enabled_v999"},
        ),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_orchestration_pattern"
    assert submitted_backtests == []


@pytest.mark.parametrize("pattern_key", SUPPORTED_NON_DEFAULT_BACKTEST_PATTERN_KEYS)
def test_create_backtest_accepts_supported_non_default_orchestration_pattern_keys(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
    pattern_key: str,
) -> None:
    portfolio = create_portfolio(
        client,
        name=f"Pattern {pattern_key}",
        slug=f"pattern_{pattern_key}",
    )
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name=f"Template {pattern_key}", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"orchestrationPatternKey": pattern_key},
        ),
    )

    assert response.status_code == 201, response.json()
    assert response.json()["orchestrationPatternKey"] == pattern_key
    assert submitted_backtests == [response.json()["id"]]

    with session_factory() as session:
        backtest = session.get(Backtest, response.json()["id"])
        assert backtest is not None
        assert backtest.launch_mode == "internal"
        assert backtest.workflow_spec_key == pattern_key
        assert backtest.workflow_spec_version == 1
        assert backtest.execution_owner == "legacy_path"


@pytest.mark.parametrize(
    "pattern_key",
    SUPPORTED_BACKTEST_PATTERN_KEYS,
)
def test_create_backtest_accepts_known_orchestration_pattern_keys_in_legacy_callback_mode(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
    pattern_key: str,
) -> None:
    portfolio = create_portfolio(
        client,
        name=f"Legacy {pattern_key}",
        slug=f"legacy_{pattern_key}",
    )
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name=f"Legacy {pattern_key} Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={
                "launchMode": "legacy_callback",
                "webhookUrl": "http://localhost:8765/webhook/legacy",
                "webhookTimeout": 90,
                "orchestrationPatternKey": pattern_key,
            },
        ),
    )

    assert response.status_code == 201, response.json()
    created = response.json()
    expected_read_fields = {
        "id": created["id"],
        "status": "PENDING",
        "orchestrationPatternKey": pattern_key,
        "webhookUrl": "http://localhost:8765/webhook/legacy",
        "webhookTimeout": 90,
        "results": None,
    }
    assert {key: created[key] for key in expected_read_fields} == expected_read_fields
    assert submitted_backtests == [created["id"]]

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert {
        key: list_response.json()[0][key] for key in expected_read_fields
    } == expected_read_fields

    get_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert get_response.status_code == 200
    assert {key: get_response.json()[key] for key in expected_read_fields} == expected_read_fields

    with session_factory() as session:
        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        assert backtest.launch_mode == "legacy_callback"
        assert backtest.workflow_spec_key is None
        assert backtest.workflow_spec_version is None
        assert backtest.execution_owner == "legacy_path"


def test_create_backtest_internal_runtime_flag_enabled_pins_runtime_v2_owner(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        RuntimeControlService(session).set_backtest_runtime_v2_enabled(
            enabled=True,
            actor="test-suite",
            reason="exercise create-time routing",
        )

    portfolio = create_portfolio(client, name="Runtime Routed", slug="runtime_routed")
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Runtime Routed Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(portfolio["id"], template_id=template["id"]),
    )

    assert response.status_code == 201, response.json()
    assert submitted_backtests == [response.json()["id"]]

    with session_factory() as session:
        backtest = session.get(Backtest, response.json()["id"])
        assert backtest is not None
        assert backtest.launch_mode == "internal"
        assert backtest.workflow_spec_key == "seeded_internal_backtest_v1"
        assert backtest.workflow_spec_version == 1
        assert backtest.execution_owner == "runtime_v2"


def test_create_backtest_uses_largest_deposit_balance(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Balance Selection", slug="balance_selection")
    smaller = create_balance(client, str(portfolio["id"]), label="Cash A", amount="1000.00")
    larger = create_balance(client, str(portfolio["id"]), label="Cash B", amount="2500.00")
    create_balance(
        client,
        str(portfolio["id"]),
        label="Taxes",
        amount="300.00",
        operation_type="WITHDRAWAL",
    )
    template = create_template(client, name="Balance Template", content="# Template")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"name": "Balance Selection Backtest"},
        ),
    )
    assert response.status_code == 201, response.json()
    assert response.json()["depositBalanceId"] == larger["id"]
    assert response.json()["depositBalanceId"] != smaller["id"]
    assert submitted_backtests == [response.json()["id"]]


def test_create_backtest_can_auto_create_default_template(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Monthly", slug="monthly")
    create_balance(client, str(portfolio["id"]), amount="5000.00")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=None,
            create_template=True,
            template_name="Portfolio Backtest Default",
            overrides={
                "name": "Monthly Backtest",
                "frequency": "MONTHLY",
                "endDate": "2024-12-31",
                "commissionMode": "FIXED",
                "commissionValue": "1.00",
                "benchmarkSymbols": ["^GSPC", "^IXIC"],
            },
        ),
    )
    assert response.status_code == 201, response.json()
    assert response.json()["templateId"] is not None
    assert submitted_backtests == [response.json()["id"]]


def test_create_backtest_rejects_missing_template_selection(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Invalid", slug="invalid")
    create_balance(client, str(portfolio["id"]), amount="5000.00")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=None,
            create_template=False,
            overrides={"name": "Invalid Backtest", "frequency": "MONTHLY", "endDate": "2024-12-31"},
        ),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "missing_template"


def test_create_backtest_rejects_null_required_text_fields(client: TestClient) -> None:
    portfolio = create_portfolio(client, name="Null Guard", slug="null_guard")
    create_balance(client, str(portfolio["id"]), amount="5000.00")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=None,
            create_template=True,
            template_name="Null Guard Template",
            overrides={
                "name": None,
            },
        ),
    )

    assert response.status_code == 422


def test_create_backtest_defaults_to_internal_launch_mode_without_callback_fields(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Internal Default", slug="internal_default")
    create_balance(client, str(portfolio["id"]), amount="5000.00")
    template = create_template(client, name="Internal Default Template", content="# Internal")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"webhookUrl": None, "webhookTimeout": None},
        ),
    )

    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["webhookUrl"] == "internal://ledger"
    assert created["webhookTimeout"] == 600
    assert submitted_backtests == [created["id"]]


def test_create_backtest_requires_callback_fields_only_in_legacy_callback_mode(
    client: TestClient,
) -> None:
    portfolio = create_portfolio(client, name="Legacy Callback", slug="legacy_callback")
    create_balance(client, str(portfolio["id"]), amount="5000.00")
    template = create_template(client, name="Legacy Callback Template", content="# Legacy")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={
                "launchMode": "legacy_callback",
                "webhookUrl": None,
                "webhookTimeout": None,
            },
        ),
    )

    assert response.status_code == 422
    assert "Legacy callback mode requires" in response.text


def test_backtest_get_returns_webhook_fields(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Redaction", slug="redaction")
    balance = create_balance(client, str(portfolio["id"]), amount="5000.00")
    template = create_template(client, name="Redaction Template", content="# Backtest")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"name": "Daily Redaction Backtest"},
        ),
    )
    assert response.status_code == 201, response.json()
    created = response.json()
    assert created["webhookUrl"] == "http://localhost:5678/webhook/test"
    assert created["webhookTimeout"] == 600
    assert created["depositBalanceId"] == balance["id"]
    assert submitted_backtests == [created["id"]]

    get_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["webhookUrl"] == "http://localhost:5678/webhook/test"
    assert get_response.json()["webhookTimeout"] == 600


def test_backtest_routes_hide_internal_run_state_results_for_tool_enabled_reads(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    portfolio = create_portfolio(client, name="Run State Hidden", slug="run_state_hidden")
    create_balance(client, str(portfolio["id"]), amount="5000.00")
    template = create_template(client, name="Run State Hidden Template", content="# Hidden")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"orchestrationPatternKey": "analyst_reviewer_tool_enabled_v1"},
        ),
    )
    assert response.status_code == 201, response.json()
    created = response.json()
    assert submitted_backtests == [created["id"]]

    with session_factory() as session:
        from app.models.backtest import Backtest

        backtest = session.get(Backtest, created["id"])
        assert backtest is not None
        backtest.status = "RUNNING"
        backtest.current_cycle_status = "AWAITING_CALLBACK"
        backtest.results = {
            "_run_state": {
                "schedule": ["2024-01-02", "2024-01-03"],
                "benchmark_history": {"^GSPC": []},
                "trade_log": [],
                "equity_points": [],
            }
        }
        session.commit()

    expected_read_fields = {
        "id": created["id"],
        "status": "RUNNING",
        "currentCycleStatus": "AWAITING_CALLBACK",
        "orchestrationPatternKey": "analyst_reviewer_tool_enabled_v1",
        "webhookUrl": "http://localhost:5678/webhook/test",
        "webhookTimeout": 600,
        "results": None,
    }

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert {
        key: list_response.json()[0][key] for key in expected_read_fields
    } == expected_read_fields

    get_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert get_response.status_code == 200
    assert {key: get_response.json()[key] for key in expected_read_fields} == expected_read_fields


def test_backtest_routes_hide_internal_routing_fields_on_reads(
    client: TestClient,
    submitted_backtests: list[int],
) -> None:
    portfolio = create_portfolio(client, name="Hidden Routing", slug="hidden_routing")
    create_balance(client, str(portfolio["id"]), amount="5000.00")
    template = create_template(client, name="Hidden Routing Template", content="# Hidden Routing")

    response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(portfolio["id"], template_id=template["id"]),
    )
    assert response.status_code == 201, response.json()
    created = response.json()
    assert submitted_backtests == [created["id"]]

    hidden_fields = {
        "launchMode",
        "workflowSpecKey",
        "workflowSpecVersion",
        "executionOwner",
        "currentRunId",
        "lastCompletedRunId",
        "launchModeClassifiedAt",
        "launchModeClassifiedBy",
        "launchModeClassificationNote",
    }
    assert hidden_fields.isdisjoint(created)

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert hidden_fields.isdisjoint(list_response.json()[0])

    get_response = client.get(f"/api/v1/backtests/{created['id']}")
    assert get_response.status_code == 200
    assert hidden_fields.isdisjoint(get_response.json())


def test_cancel_backtest_marks_running_job_cancelled(
    client: TestClient, submitted_backtests: list[int]
) -> None:
    portfolio = create_portfolio(client, name="Cancelable", slug="cancelable")
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Cancel Template", content="# Cancel")

    create_response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"], template_id=template["id"], overrides={"name": "Cancelable Backtest"}
        ),
    )
    assert create_response.status_code == 201, create_response.json()
    backtest_id = create_response.json()["id"]
    assert submitted_backtests == [backtest_id]

    cancel_response = client.post(f"/api/v1/backtests/{backtest_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "CANCELLED"


def test_delete_backtest_requires_terminal_state_and_cleans_reports_and_trades(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    portfolio = create_portfolio(client, name="Cleanup", slug="cleanup")
    balance = create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Cleanup Template", content="# Cleanup")
    create_response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"], template_id=template["id"], overrides={"name": "Cleanup Backtest"}
        ),
    )
    assert create_response.status_code == 201, create_response.json()
    completed_backtest = create_response.json()
    assert submitted_backtests == [completed_backtest["id"]]

    with session_factory() as session:
        from app.models.backtest import Backtest

        backtest = session.get(Backtest, completed_backtest["id"])
        assert backtest is not None
        backtest.status = "COMPLETED"
        session.add(
            TradingOperation(
                portfolio_id=portfolio["id"],
                balance_id=balance["id"],
                backtest_id=completed_backtest["id"],
                balance_label="Cash",
                symbol="AAPL",
                side="BUY",
                quantity=Decimal("5"),
                price=Decimal("184.40"),
                commission=Decimal("0"),
                currency="USD",
                executed_at=datetime(2024, 1, 15, 20, 30, tzinfo=dt.timezone.utc),  # noqa: UP017
            )
        )
        session.add(
            Report(
                name=f"backtest_{completed_backtest['id']}_20240115",
                slug=f"backtest_{completed_backtest['id']}_20240115",
                source="external",
                content="# Backtest report",
                metadata_={"tags": ["backtest", f"backtest_{completed_backtest['id']}"]},
            )
        )
        session.commit()

    delete_response = client.delete(f"/api/v1/backtests/{completed_backtest['id']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/backtests/{completed_backtest['id']}").status_code == 404

    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count(TradingOperation.id)).where(
                    TradingOperation.backtest_id == completed_backtest["id"]
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count(Report.id)).where(
                    Report.slug == f"backtest_{completed_backtest['id']}_20240115"
                )
            )
            == 0
        )


def test_delete_backtest_cascades_orchestration_snapshots(
    client: TestClient,
    submitted_backtests: list[int],
    session_factory: sessionmaker[Session],
) -> None:
    from app.models.backtest import Backtest
    from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot

    portfolio = create_portfolio(client, name="Snapshot Cleanup", slug="snapshot_cleanup")
    create_balance(client, str(portfolio["id"]), amount="10000.00")
    template = create_template(client, name="Snapshot Cleanup Template", content="# Cleanup")

    create_response = client.post(
        "/api/v1/backtests",
        json=build_backtest_payload(
            portfolio["id"],
            template_id=template["id"],
            overrides={"name": "Snapshot Cleanup Backtest"},
        ),
    )
    assert create_response.status_code == 201, create_response.json()
    backtest_id = create_response.json()["id"]
    assert submitted_backtests == [backtest_id]

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.status = "COMPLETED"
        session.add(
            BacktestOrchestrationSnapshot(
                backtest_id=backtest_id,
                cycle_date=date(2024, 1, 15),
                prompt_report_slug=f"backtest_{backtest_id}_prompt_20240115",
                orchestration_pattern_key="analyst_reviewer_v1",
                pattern_policy_version=1,
                entry_prompt_hash="1" * 64,
                full_user_prompt_hash="2" * 64,
                resolved_mentions=[
                    {
                        "original_text": "@analyst",
                        "handle": "analyst",
                        "canonical_target_id": "character:analyst",
                        "target_type": "character",
                        "role_id": 1,
                        "role_version": 3,
                        "character_id": 1,
                        "character_version": 4,
                        "mention_order": 0,
                    }
                ],
                mentioned_target_outputs=[
                    {
                        "handle": "analyst",
                        "canonical_target_id": "character:analyst",
                        "output_markdown": "summary",
                    }
                ],
                resolved_builtin_versions=[],
                resolved_role_versions=[
                    {"canonical_target_id": "role:analyst_role", "role_id": 1, "version": 3}
                ],
                resolved_character_versions=[
                    {
                        "canonical_target_id": "character:analyst",
                        "character_id": 1,
                        "version": 4,
                    }
                ],
            )
        )
        session.commit()

    delete_response = client.delete(f"/api/v1/backtests/{backtest_id}")
    assert delete_response.status_code == 204

    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count(BacktestOrchestrationSnapshot.id)).where(
                    BacktestOrchestrationSnapshot.backtest_id == backtest_id
                )
            )
            == 0
        )


def test_init_db_marks_interrupted_backtests_failed(database_url: str) -> None:
    from app.models.backtest import Backtest

    init_db(database_url)
    session_factory = get_session_factory(database_url)

    with session_factory() as session:
        portfolio = Portfolio(
            name="Interrupted", slug="interrupted", description=None, base_currency="USD"
        )
        session.add(portfolio)
        session.flush()

        balance = Balance(
            portfolio_id=portfolio.id,
            label="Cash",
            operation_type="DEPOSIT",
            amount=Decimal("10000.00"),
            currency="USD",
        )
        template = TextTemplate(name="Interrupted Template", content="# Template")
        session.add_all([balance, template])
        session.flush()

        session.add(
            Backtest(
                portfolio_id=portfolio.id,
                deposit_balance_id=balance.id,
                name="Interrupted Backtest",
                status="RUNNING",
                frequency="DAILY",
                start_date=date(2024, 1, 2),
                end_date=date(2024, 1, 31),
                total_cycles=21,
                completed_cycles=7,
                template_id=template.id,
                webhook_url="http://localhost:5678/webhook/test",
                webhook_timeout=600,
                price_mode="CLOSING_PRICE",
                commission_mode="ZERO",
                commission_value=Decimal("0"),
                benchmark_symbols=["^GSPC"],
            )
        )
        session.commit()

    init_db(database_url)

    with session_factory() as session:
        backtest = session.scalar(select(Backtest).where(Backtest.name == "Interrupted Backtest"))
        assert backtest is not None
        assert backtest.status == "FAILED"
        assert "Process interrupted" in (backtest.error_message or "")


def test_init_db_marks_interrupted_backtests_failed_for_legacy_backtests_table(
    database_url: str,
) -> None:
    engine = get_engine(database_url)

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE backtests (
                id INTEGER PRIMARY KEY,
                status VARCHAR NOT NULL,
                error_message TEXT
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO backtests (id, status, error_message) VALUES (1, 'RUNNING', NULL)"
        )

    init_db(database_url)

    with engine.connect() as connection:
        row = connection.exec_driver_sql(
            "SELECT status, error_message FROM backtests WHERE id = 1"
        ).one()

    assert row[0] == "FAILED"
    assert "Process interrupted" in (row[1] or "")


def test_backtest_read_accepts_failure_reason_in_recent_activity() -> None:
    read_model = BacktestRead.model_validate(
        {
            "id": 7,
            "portfolio_id": 1,
            "template_id": 2,
            "deposit_balance_id": 3,
            "name": "Contract Check",
            "status": "FAILED",
            "frequency": "DAILY",
            "start_date": date(2024, 1, 2),
            "end_date": date(2024, 3, 29),
            "current_cycle_date": None,
            "total_cycles": 3,
            "completed_cycles": 1,
            "webhook_url": "http://localhost:5678/webhook/test",
            "webhook_timeout": 600,
            "price_mode": "CLOSING_PRICE",
            "commission_mode": "ZERO",
            "commission_value": Decimal("0"),
            "benchmark_symbols": ["^GSPC"],
            "recent_activity": [
                {
                    "cycleDate": "2024-02-29",
                    "decisions": [
                        {
                            "symbol": "AAPL",
                            "action": "BUY",
                            "reasoning": "Breakout setup invalidated.",
                            "failureReason": "No market data for symbol",
                        }
                    ],
                }
            ],
            "results": None,
            "error_message": "No market data for symbol",
            "created_at": datetime(2024, 1, 2, 12, 0, tzinfo=dt.timezone.utc),  # noqa: UP017
            "updated_at": datetime(2024, 1, 2, 12, 5, tzinfo=dt.timezone.utc),  # noqa: UP017
        }
    )

    assert read_model.recent_activity is not None
    assert read_model.recent_activity[0].decisions[0].failure_reason == "No market data for symbol"


def test_backtest_read_ignores_internal_run_state_results_payload() -> None:
    read_model = BacktestRead.model_validate(
        {
            "id": 8,
            "portfolio_id": 1,
            "template_id": 2,
            "deposit_balance_id": 3,
            "name": "In Flight Backtest",
            "orchestration_pattern_key": "analyst_reviewer_v1",
            "status": "AWAITING_CALLBACK",
            "frequency": "DAILY",
            "start_date": date(2024, 1, 2),
            "end_date": date(2024, 1, 3),
            "current_cycle_date": date(2024, 1, 2),
            "total_cycles": 2,
            "completed_cycles": 0,
            "webhook_url": "http://localhost:5678/webhook/test",
            "webhook_timeout": 600,
            "price_mode": "CLOSING_PRICE",
            "commission_mode": "ZERO",
            "commission_value": Decimal("0"),
            "benchmark_symbols": ["^GSPC"],
            "current_cycle_status": "AWAITING_CALLBACK",
            "recent_activity": None,
            "results": {
                "_run_state": {
                    "schedule": ["2024-01-02", "2024-01-03"],
                    "benchmark_history": {"^GSPC": []},
                    "trade_log": [],
                    "equity_points": [],
                }
            },
            "error_message": None,
            "created_at": datetime(2024, 1, 2, 12, 0, tzinfo=dt.timezone.utc),  # noqa: UP017
            "updated_at": datetime(2024, 1, 2, 12, 5, tzinfo=dt.timezone.utc),  # noqa: UP017
        }
    )

    assert read_model.orchestration_pattern_key == "analyst_reviewer_v1"
    assert read_model.results is None
    assert read_model.model_dump(by_alias=True)["results"] is None


def test_backtest_read_preserves_public_results_payload_for_tool_enabled_patterns() -> None:
    results_payload = {
        "portfolio": {
            "starting_value": Decimal("1000.00"),
            "ending_value": Decimal("1125.00"),
            "total_return": Decimal("0.125"),
            "annualized_return": Decimal("0.125"),
            "max_drawdown": Decimal("-0.05"),
            "sharpe_ratio": Decimal("1.25"),
            "total_trades": 1,
            "win_rate": Decimal("1"),
            "total_commission": Decimal("0"),
        },
        "benchmarks": {
            "^GSPC": {
                "starting_price": Decimal("5000.00"),
                "ending_price": Decimal("5100.00"),
                "total_return": Decimal("0.02"),
            }
        },
        "equity_curve": [{"date": date(2024, 1, 2), "value": Decimal("1000.00")}],
        "benchmark_curves": {"^GSPC": [{"date": date(2024, 1, 2), "value": Decimal("5000.00")}]},
        "drawdown_curve": [{"date": date(2024, 1, 2), "value": Decimal("0")}],
        "trades": [
            {
                "cycle_date": date(2024, 1, 2),
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": Decimal("1"),
                "requested_price": Decimal("180.00"),
                "executed_price": Decimal("181.00"),
                "executed": True,
                "report_slug": "report-1",
                "failure_reason": None,
                "commission": Decimal("0"),
                "profit": None,
            }
        ],
    }

    read_model = BacktestRead.model_validate(
        {
            "id": 9,
            "portfolio_id": 1,
            "template_id": 2,
            "deposit_balance_id": 3,
            "name": "Completed Tool-Enabled Backtest",
            "orchestration_pattern_key": "analyst_reviewer_tool_enabled_v1",
            "status": "COMPLETED",
            "frequency": "DAILY",
            "start_date": date(2024, 1, 2),
            "end_date": date(2024, 1, 3),
            "current_cycle_date": None,
            "total_cycles": 2,
            "completed_cycles": 2,
            "webhook_url": "http://localhost:5678/webhook/test",
            "webhook_timeout": 600,
            "price_mode": "CLOSING_PRICE",
            "commission_mode": "ZERO",
            "commission_value": Decimal("0"),
            "benchmark_symbols": ["^GSPC"],
            "current_cycle_status": None,
            "recent_activity": None,
            "results": results_payload,
            "error_message": None,
            "created_at": datetime(2024, 1, 2, 12, 0, tzinfo=dt.timezone.utc),  # noqa: UP017
            "updated_at": datetime(2024, 1, 2, 12, 5, tzinfo=dt.timezone.utc),  # noqa: UP017
        }
    )

    assert read_model.orchestration_pattern_key == "analyst_reviewer_tool_enabled_v1"
    assert read_model.results is not None
    assert read_model.model_dump(mode="json", by_alias=True)["results"] == {
        "portfolio": {
            "startingValue": "1000.00",
            "endingValue": "1125.00",
            "totalReturn": "0.125",
            "annualizedReturn": "0.125",
            "maxDrawdown": "-0.05",
            "sharpeRatio": "1.25",
            "totalTrades": 1,
            "winRate": "1",
            "totalCommission": "0",
        },
        "benchmarks": {
            "^GSPC": {
                "startingPrice": "5000.00",
                "endingPrice": "5100.00",
                "totalReturn": "0.02",
            }
        },
        "equityCurve": [{"date": "2024-01-02", "value": "1000.00"}],
        "benchmarkCurves": {"^GSPC": [{"date": "2024-01-02", "value": "5000.00"}]},
        "drawdownCurve": [{"date": "2024-01-02", "value": "0"}],
        "trades": [
            {
                "cycleDate": "2024-01-02",
                "symbol": "AAPL",
                "side": "BUY",
                "quantity": "1",
                "requestedPrice": "180.00",
                "executedPrice": "181.00",
                "executed": True,
                "reportSlug": "report-1",
                "failureReason": None,
                "commission": "0",
                "profit": None,
            }
        ],
    }
