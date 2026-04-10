# pyright: reportMissingImports=false

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.orchestration_character import OrchestrationCharacter
from app.models.orchestration_role import OrchestrationRole
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate
from app.schemas.backtest import BacktestStatus
from app.services.backtest_cycle_service import BacktestCycleService
from app.services.backtest_engine import BacktestEngine

ANALYST_SUMMARY = "Review the backtest from the analyst perspective and summarize the tradeoffs."


def compact_artifact_text(value: str) -> str:
    normalized = " ".join(value.split())
    return normalized or "none"


def expected_builtin_artifact(
    description: str,
    *,
    compiled_entry_prompt_body: str,
    execution_context_body: str,
) -> str:
    return (
        f"{description} Entry prompt focus: "
        f"{compact_artifact_text(compiled_entry_prompt_body)}. "
        f"Execution context focus: {compact_artifact_text(execution_context_body)}."
    )


def expected_character_artifact(
    *,
    role_name: str,
    role_system_prompt: str,
    character_prompt_append: str | None,
    compiled_entry_prompt_body: str,
    execution_context_body: str,
) -> str:
    character_guidance = (
        compact_artifact_text(character_prompt_append)
        if character_prompt_append and character_prompt_append.strip()
        else "No character-specific guidance provided"
    )
    return (
        f"{role_name} execution brief. "
        f"System prompt: {compact_artifact_text(role_system_prompt)}. "
        f"Character guidance: {character_guidance}. "
        f"Entry prompt focus: {compact_artifact_text(compiled_entry_prompt_body)}. "
        f"Execution context focus: {compact_artifact_text(execution_context_body)}."
    )


def build_service() -> BacktestCycleService:
    return BacktestCycleService(
        cast(Session, SimpleNamespace()),
        cast(sessionmaker[Session], SimpleNamespace()),
    )


def create_backtest(
    session_factory: sessionmaker[Session],
    *,
    current_cycle_date: date | None,
    current_cycle_status: str | None,
) -> int:
    with session_factory() as session:
        portfolio = Portfolio(
            name="Timeout Portfolio", slug="timeout_portfolio", base_currency="USD"
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
        template = TextTemplate(name="Timeout Template", content="# Timeout")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name="Timeout Backtest",
            status=BacktestStatus.RUNNING.value,
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
            current_cycle_date=current_cycle_date,
            current_cycle_status=current_cycle_status,
        )
        session.add(backtest)
        session.commit()
        return backtest.id


def create_orchestration_character(
    session_factory: sessionmaker[Session],
    *,
    handle: str,
    role_key: str,
    role_name: str,
    role_description: str = "",
    role_system_prompt: str = "Role prompt",
    role_enabled: bool = True,
    character_description: str = "",
    character_prompt_append: str = "",
    character_enabled: bool = True,
) -> OrchestrationCharacter:
    with session_factory() as session:
        role = OrchestrationRole(
            key=role_key,
            name=role_name,
            description=role_description or None,
            system_prompt=role_system_prompt,
            enabled=role_enabled,
        )
        session.add(role)
        session.flush()
        character = OrchestrationCharacter(
            handle=handle,
            display_name=role_name,
            description=character_description or None,
            role_id=role.id,
            prompt_append=character_prompt_append or None,
            enabled=character_enabled,
        )
        session.add(character)
        session.commit()
        session.refresh(character)
        return character


class FakeEngine:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.apply_calls: list[dict[str, Any]] = []
        self.record_calls: list[tuple[date, dict[str, dict[str, Decimal]]]] = []
        self.finalize_calls: list[dict[str, Any]] = []

    def _portfolio_symbols(self) -> list[str]:
        return self.symbols

    def apply_cycle_trades(
        self,
        *,
        cycle_date: date,
        decisions: list[Any],
        market_data: dict[str, dict[str, Decimal]],
        report_slug: str | None = None,
    ) -> list[dict[str, Any]]:
        call = {
            "cycle_date": cycle_date,
            "decisions": decisions,
            "market_data": market_data,
            "report_slug": report_slug,
        }
        self.apply_calls.append(call)
        return [
            {
                "symbol": decision.symbol,
                "side": decision.action,
                "executed": None,
                "reportSlug": report_slug,
            }
            for decision in decisions
        ]

    def record_cycle_equity(
        self, cycle_date: date, market_data: dict[str, dict[str, Decimal]]
    ) -> tuple[str, Decimal]:
        self.record_calls.append((cycle_date, market_data))
        return cycle_date.isoformat(), Decimal("100000.00")

    def finalize(
        self,
        *,
        equity_points: list[tuple[str, Decimal]],
        benchmark_history: dict[str, list[tuple[str, Decimal]]],
        trade_log: list[dict[str, Any]],
        schedule: list[date],
    ) -> None:
        self.finalize_calls.append(
            {
                "equity_points": equity_points,
                "benchmark_history": benchmark_history,
                "trade_log": trade_log,
                "schedule": schedule,
            }
        )


class FakeRunner:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def run_cycle(self, request: Any) -> Any:
        self.requests.append(request)
        return SimpleNamespace(report_content="", decisions=[])


class PromptStoringEngine(FakeEngine):
    def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
        _ = (requested_cycle_date, analysis)
        return "report"


@pytest.mark.parametrize(
    ("status"),
    [
        BacktestStatus.FAILED.value,
        BacktestStatus.CANCELLED.value,
        BacktestStatus.COMPLETED.value,
    ],
)
def test_validate_cycle_status_rejects_terminal_backtests(status: str) -> None:
    service = build_service()
    backtest = SimpleNamespace(
        status=status, current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value
    )

    with pytest.raises(ApiError, match=f"Backtest is {status}, cannot process callbacks") as exc:
        service._validate_cycle_status(
            cast(Backtest, backtest),
            date(2024, 6, 17),
            allow=[BacktestStatus.AWAITING_CALLBACK.value],
        )

    assert exc.value.code == "invalid_backtest_state"


def test_validate_cycle_status_rejects_unexpected_cycle_status() -> None:
    service = build_service()
    backtest = SimpleNamespace(
        status=BacktestStatus.RUNNING.value,
        current_cycle_status=None,
        current_cycle_date=None,
    )

    with pytest.raises(ApiError, match="expected one of") as exc:
        service._validate_cycle_status(
            cast(Backtest, backtest),
            date(2024, 6, 17),
            allow=[BacktestStatus.AWAITING_CALLBACK.value],
        )

    assert exc.value.code == "invalid_backtest_cycle_status"


def test_deterministic_cycle_buys_starter_position_for_empty_portfolio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    engine = FakeEngine([])
    cycle_date = date(2024, 6, 17)
    market_data = {
        "AAPL": {
            "open": Decimal("183.50"),
            "high": Decimal("185.00"),
            "low": Decimal("183.25"),
            "close": Decimal("184.40"),
            "volume": Decimal("1000000"),
        }
    }

    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._deterministic_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx={"market_data": market_data, "prompt_report_slug": "prompt-42"},
    )

    decision = engine.apply_calls[0]["decisions"][0]
    assert decision.symbol == "AAPL"
    assert decision.action == "BUY"
    assert decision.quantity == 2
    assert decision.reasoning == "Deterministic starter position"
    assert engine.record_calls == [(cycle_date, market_data)]
    assert len(engine.finalize_calls) == 1


def test_deterministic_cycle_holds_existing_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    service = build_service()
    engine = FakeEngine(["AAPL", "MSFT"])
    cycle_date = date(2024, 6, 17)
    market_data = {
        "AAPL": {"close": Decimal("184.40")},
        "MSFT": {"close": Decimal("430.10")},
    }

    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._deterministic_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx={"market_data": market_data, "prompt_report_slug": "prompt-42"},
    )

    decisions = engine.apply_calls[0]["decisions"]
    assert [(decision.symbol, decision.action, decision.quantity) for decision in decisions] == [
        ("AAPL", "HOLD", None),
        ("MSFT", "HOLD", None),
    ]


def test_deterministic_cycle_validates_mentions_before_applying_trades(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    engine = FakeEngine(["AAPL"])
    cycle_date = date(2024, 6, 17)
    market_data = {"AAPL": {"close": Decimal("184.40")}}

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: cast(
            Backtest,
            SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    with pytest.raises(ApiError, match="Mention target @ghost was not found") as exc:
        service._deterministic_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, engine),
            cycle_ctx={
                "market_data": market_data,
                "prompt_report_slug": "prompt-42",
                "authored_entry_prompt_body": "@ghost",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
            },
        )

    assert exc.value.code == "mention_target_not_found"
    assert engine.apply_calls == []


def test_run_internal_cycle_passes_expanded_prompt_bundle_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()

    class StoredReportEngine(FakeEngine):
        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            _ = (requested_cycle_date, analysis)
            return "report"

    engine = StoredReportEngine(["AAPL"])
    cycle_date = date(2024, 6, 17)
    cycle_ctx = {
        "prompt_report_slug": "prompt-42",
        "market_data": {"AAPL": {"close": Decimal("184.40")}},
        "authored_entry_prompt_body": "authored entry prompt",
        "compiled_entry_prompt_body": "compiled entry prompt",
        "execution_context_body": "execution context",
        "full_user_prompt": "full user prompt",
    }

    monkeypatch.setattr(
        service,
        "_load_prompt_report",
        lambda prompt_report_slug: "# prompt report",
    )
    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="pattern"),
    )

    captured: dict[str, Any] = {}

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(report_content="", decisions=[])

    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: FakeRunner()
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx=cycle_ctx,
    )

    request = captured["request"]
    assert request.authored_entry_prompt_body == "authored entry prompt"
    assert request.compiled_entry_prompt_body == "compiled entry prompt"
    assert request.execution_context_body == "execution context"
    assert request.full_user_prompt == "full user prompt"


def test_mentions_are_parsed_from_authored_entry_prompt_body_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "Search @librarian only here.",
            "compiled_entry_prompt_body": "compiled body without mentions",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff without mention parsing",
            "market_data": {},
        },
    )

    request = captured["request"]
    assert request.authored_entry_prompt_body == "Search @librarian only here."
    assert request.full_user_prompt != "runtime handoff without mention parsing"
    assert "@librarian" not in request.full_user_prompt


def test_invalid_sequences_like_double_at_remain_literal_and_do_not_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "Literal @@librarian should stay text.",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    request = captured["request"]
    assert "@@librarian" in request.authored_entry_prompt_body
    assert request.full_user_prompt == "runtime handoff"


def test_mentions_normalize_handles_ignore_email_text_and_preserve_first_global_order(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": (
                "Email qa@example.com then @ANALYST then @Librarian "
                "then @analyst again and @EXPLORE"
            ),
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    request = captured["request"]
    assert getattr(request, "mentioned_target_outputs", None) == (
        "character:analyst",
        "builtin:librarian",
        "builtin:explore",
    )
    assert [mention["handle"] for mention in request.resolved_mentions] == [
        "analyst",
        "librarian",
        "explore",
    ]


def test_builtin_mentions_are_validated_against_pattern_policy_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    runner_called: list[bool] = []

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "_resolve_pattern_mention_policy",
        lambda pattern_key: SimpleNamespace(
            version=7,
            allow_characters=False,
            allowed_builtin_handles=(),
        ),
    )

    def fake_run_cycle(request: Any) -> Any:
        runner_called.append(True)
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    with pytest.raises(
        ApiError,
        match=(
            "Mention target @explore is not allowed by orchestration pattern "
            "seeded_internal_backtest_v1"
        ),
    ) as exc:
        service._run_internal_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
            cycle_ctx={
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "authored_entry_prompt_body": "@explore",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
                "market_data": {},
            },
        )

    assert exc.value.code == "mention_target_not_allowed_by_pattern"
    assert runner_called == []


def test_snapshot_persists_explicit_builtin_snapshot_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}
    snapshot_calls: list[dict[str, Any]] = []

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "_store_orchestration_snapshot",
        lambda **kwargs: snapshot_calls.append(kwargs),
        raising=False,
    )

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    librarian_artifact = expected_builtin_artifact(
        "Research and retrieve supporting context for a backtest analysis.",
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context",
    )
    expected_full_user_prompt = (
        "execution context\n\n## Mentioned Target Outputs\n"
        f"- librarian: {librarian_artifact}\n\n"
        "compiled body"
    )

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@librarian",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    assert snapshot_calls == [
        {
            "backtest_id": 42,
            "cycle_date": cycle_date,
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "orchestration_pattern_key": "seeded_internal_backtest_v1",
            "pattern_policy_version": 1,
            "entry_prompt_hash": hashlib.sha256(b"@librarian").hexdigest(),
            "full_user_prompt_hash": hashlib.sha256(
                expected_full_user_prompt.encode("utf-8")
            ).hexdigest(),
            "resolved_mentions": [
                {
                    "original_text": "@librarian",
                    "handle": "librarian",
                    "canonical_target_id": "builtin:librarian",
                    "target_type": "builtin",
                    "role_id": None,
                    "role_version": None,
                    "character_id": None,
                    "character_version": None,
                    "mention_order": 0,
                }
            ],
            "mentioned_target_outputs": [
                {
                    "handle": "librarian",
                    "canonical_target_id": "builtin:librarian",
                    "target_type": "builtin",
                    "output_markdown": librarian_artifact,
                }
            ],
            "resolved_builtin_versions": [
                {
                    "canonical_target_id": "builtin:librarian",
                    "handle": "librarian",
                    "revision": 1,
                }
            ],
            "resolved_role_versions": [],
            "resolved_character_versions": [],
        }
    ]
    assert captured["request"].full_user_prompt == expected_full_user_prompt


def test_character_mentions_resolve_to_canonical_ids_and_dedupe(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )
    create_orchestration_character(
        session_factory,
        handle="reviewer",
        role_key="reviewer_role",
        role_name="Reviewer Role",
        character_description="Review the backtest conservatively and call out execution risks.",
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst then @analyst again and @reviewer",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    request = captured["request"]
    assert getattr(request, "mentioned_target_outputs", None) == (
        "character:analyst",
        "character:reviewer",
    )


def test_seeded_internal_backtest_v1_rejects_character_mentions(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    with pytest.raises(
        ApiError,
        match=(
            "Mention target @analyst is not allowed by orchestration pattern "
            "seeded_internal_backtest_v1"
        ),
    ) as exc:
        service._run_internal_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
            cycle_ctx={
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "authored_entry_prompt_body": "@analyst",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
                "market_data": {},
            },
        )

    assert exc.value.code == "mention_target_not_allowed_by_pattern"


def test_analyst_reviewer_v1_allows_character_mentions(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    request = captured["request"]
    analyst_artifact = expected_character_artifact(
        role_name="Analyst Role",
        role_system_prompt="Role prompt",
        character_prompt_append=None,
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context",
    )
    assert request.full_user_prompt == (
        "execution context\n\n## Mentioned Target Outputs\n"
        f"- analyst: {analyst_artifact}\n\n"
        "compiled body"
    )


def test_character_execution_artifacts_include_role_prompt_bundle_before_runner_execution(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}
    snapshot_calls: list[dict[str, Any]] = []

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        role_system_prompt="Review the cycle with explicit risk controls.",
        character_prompt_append="Focus on balance-sheet durability first.",
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "_store_orchestration_snapshot",
        lambda **kwargs: snapshot_calls.append(kwargs),
        raising=False,
    )

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    analyst_artifact = expected_character_artifact(
        role_name="Analyst Role",
        role_system_prompt="Review the cycle with explicit risk controls.",
        character_prompt_append="Focus on balance-sheet durability first.",
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context",
    )

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    assert captured["request"].full_user_prompt == (
        "execution context\n\n## Mentioned Target Outputs\n"
        f"- analyst: {analyst_artifact}\n\n"
        "compiled body"
    )
    assert snapshot_calls[0]["mentioned_target_outputs"] == [
        {
            "handle": "analyst",
            "canonical_target_id": "character:analyst",
            "target_type": "character",
            "output_markdown": analyst_artifact,
        }
    ]


def test_unknown_mention_fails_cycle_with_clear_error(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    with pytest.raises(ApiError, match="Mention target @ghost was not found") as exc:
        service._run_internal_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
            cycle_ctx={
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "authored_entry_prompt_body": "@ghost",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
                "market_data": {},
            },
        )

    assert exc.value.code == "mention_target_not_found"
    assert runner.requests == []


def test_disabled_character_fails_cycle_with_character_role_disabled_or_target_disabled(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
        character_enabled=False,
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    with pytest.raises(ApiError, match="Mention target @analyst is disabled") as exc:
        service._run_internal_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
            cycle_ctx={
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "authored_entry_prompt_body": "@analyst",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
                "market_data": {},
            },
        )

    assert exc.value.code == "mention_target_disabled"
    assert runner.requests == []


def test_execution_rejects_character_when_role_is_disabled_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        role_enabled=True,
        character_description=ANALYST_SUMMARY,
    )
    with session_factory() as session:
        role = session.query(OrchestrationRole).filter_by(key="analyst_role").one()
        role.enabled = False
        session.commit()

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    with pytest.raises(ApiError, match="Character role for @analyst is disabled") as exc:
        service._run_internal_cycle(
            backtest_id=42,
            cycle_date=cycle_date,
            engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
            cycle_ctx={
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "authored_entry_prompt_body": "@analyst",
                "compiled_entry_prompt_body": "compiled body",
                "execution_context_body": "execution context",
                "full_user_prompt": "runtime handoff",
                "market_data": {},
            },
        )

    assert exc.value.code == "character_role_disabled"


def test_character_outputs_append_after_prior_reports_in_execution_context(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context\n\n## Prior Reports\n- report-a\n",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    analyst_artifact = expected_character_artifact(
        role_name="Analyst Role",
        role_system_prompt="Role prompt",
        character_prompt_append=None,
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context\n\n## Prior Reports\n- report-a\n",
    )
    assert captured["request"].full_user_prompt == (
        "execution context\n\n## Prior Reports\n- report-a\n\n"
        "## Mentioned Target Outputs\n"
        f"- analyst: {analyst_artifact}\n\n"
        "compiled body"
    )


def test_snapshot_persists_role_versions_and_character_versions_used_for_cycle(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    snapshot_calls: list[dict[str, Any]] = []

    character = create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )
    with session_factory() as session:
        role = session.query(OrchestrationRole).filter_by(key="analyst_role").one()
        expected_role_version = role.version
        expected_character_version = character.version

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        service,
        "_store_orchestration_snapshot",
        lambda **kwargs: snapshot_calls.append(kwargs),
        raising=False,
    )

    runner.run_cycle = lambda request: SimpleNamespace(report_content="", decisions=[])  # type: ignore[assignment]

    analyst_artifact = expected_character_artifact(
        role_name="Analyst Role",
        role_system_prompt="Role prompt",
        character_prompt_append=None,
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context",
    )
    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    assert snapshot_calls == [
        {
            "backtest_id": 42,
            "cycle_date": cycle_date,
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "orchestration_pattern_key": "analyst_reviewer_v1",
            "pattern_policy_version": 1,
            "entry_prompt_hash": hashlib.sha256(b"@analyst").hexdigest(),
            "full_user_prompt_hash": hashlib.sha256(
                b"execution context\n\n## Mentioned Target Outputs\n"
                + f"- analyst: {analyst_artifact}\n\n".encode()
                + b"compiled body"
            ).hexdigest(),
            "resolved_mentions": [
                {
                    "original_text": "@analyst",
                    "handle": "analyst",
                    "canonical_target_id": "character:analyst",
                    "target_type": "character",
                    "role_id": character.role_id,
                    "role_version": expected_role_version,
                    "character_id": character.id,
                    "character_version": expected_character_version,
                    "mention_order": 0,
                }
            ],
            "mentioned_target_outputs": [
                {
                    "handle": "analyst",
                    "canonical_target_id": "character:analyst",
                    "target_type": "character",
                    "output_markdown": analyst_artifact,
                }
            ],
            "resolved_builtin_versions": [],
            "resolved_role_versions": [
                {
                    "canonical_target_id": "role:analyst_role",
                    "role_id": character.role_id,
                    "version": expected_role_version,
                }
            ],
            "resolved_character_versions": [
                {
                    "canonical_target_id": "character:analyst",
                    "character_id": character.id,
                    "version": expected_character_version,
                }
            ],
        }
    ]


def test_snapshot_row_is_not_rewritten_by_later_role_or_character_edits(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot

    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    backtest_id = create_backtest(
        session_factory,
        current_cycle_date=None,
        current_cycle_status=None,
    )

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.orchestration_pattern_key = "analyst_reviewer_v1"
        session.commit()

    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    runner.run_cycle = lambda request: SimpleNamespace(report_content="", decisions=[])  # type: ignore[assignment]

    service._run_internal_cycle(
        backtest_id=backtest_id,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    with session_factory() as session:
        snapshot = (
            session.query(BacktestOrchestrationSnapshot)
            .filter_by(backtest_id=backtest_id, cycle_date=cycle_date)
            .one()
        )
        stored_snapshot = {
            "prompt_report_slug": snapshot.prompt_report_slug,
            "orchestration_pattern_key": snapshot.orchestration_pattern_key,
            "pattern_policy_version": snapshot.pattern_policy_version,
            "entry_prompt_hash": snapshot.entry_prompt_hash,
            "full_user_prompt_hash": snapshot.full_user_prompt_hash,
            "resolved_mentions": list(snapshot.resolved_mentions),
            "mentioned_target_outputs": list(snapshot.mentioned_target_outputs),
            "resolved_builtin_versions": list(snapshot.resolved_builtin_versions),
            "resolved_role_versions": list(snapshot.resolved_role_versions),
            "resolved_character_versions": list(snapshot.resolved_character_versions),
        }

    with session_factory() as session:
        role = session.query(OrchestrationRole).filter_by(key="analyst_role").one()
        character = session.query(OrchestrationCharacter).filter_by(handle="analyst").one()
        role.description = "Updated role description"
        role.version += 1
        character.description = "Updated character description"
        character.version += 1
        session.commit()
        refreshed_role_version = role.version
        refreshed_character_version = character.version

    with session_factory() as session:
        snapshot = (
            session.query(BacktestOrchestrationSnapshot)
            .filter_by(backtest_id=backtest_id, cycle_date=cycle_date)
            .one()
        )
        assert {
            "prompt_report_slug": snapshot.prompt_report_slug,
            "orchestration_pattern_key": snapshot.orchestration_pattern_key,
            "pattern_policy_version": snapshot.pattern_policy_version,
            "entry_prompt_hash": snapshot.entry_prompt_hash,
            "full_user_prompt_hash": snapshot.full_user_prompt_hash,
            "resolved_mentions": list(snapshot.resolved_mentions),
            "mentioned_target_outputs": list(snapshot.mentioned_target_outputs),
            "resolved_builtin_versions": list(snapshot.resolved_builtin_versions),
            "resolved_role_versions": list(snapshot.resolved_role_versions),
            "resolved_character_versions": list(snapshot.resolved_character_versions),
        } == stored_snapshot

    assert stored_snapshot["resolved_role_versions"][0]["version"] != refreshed_role_version
    assert (
        stored_snapshot["resolved_character_versions"][0]["version"] != refreshed_character_version
    )


def test_internal_dispatch_uses_canonical_character_target_ids_only(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    service = build_service()
    service.session_factory = session_factory
    cycle_date = date(2024, 6, 17)
    captured: dict[str, Any] = {}

    create_orchestration_character(
        session_factory,
        handle="analyst",
        role_key="analyst_role",
        role_name="Analyst Role",
        character_description=ANALYST_SUMMARY,
    )

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(report_content="", decisions=[])

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="analyst_reviewer_v1"),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: FakeRunner()
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@analyst",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "runtime handoff",
            "market_data": {},
        },
    )

    assert getattr(captured["request"], "mentioned_target_outputs", None) == ("character:analyst",)


def test_runner_receives_post_mention_full_user_prompt_as_authoritative_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    runner = FakeRunner()
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(
            orchestration_pattern_key="seeded_internal_backtest_v1"
        ),
    )
    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: runner
    )
    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)

    def fake_run_cycle(request: Any) -> Any:
        captured["request"] = request
        return SimpleNamespace(report_content="", decisions=[])

    runner.run_cycle = fake_run_cycle  # type: ignore[assignment]

    explore_artifact = expected_builtin_artifact(
        "Inspect the current backtest context and summarize relevant findings.",
        compiled_entry_prompt_body="compiled body",
        execution_context_body="execution context",
    )
    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, PromptStoringEngine(["AAPL"])),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "authored_entry_prompt_body": "@explore",
            "compiled_entry_prompt_body": "compiled body",
            "execution_context_body": "execution context",
            "full_user_prompt": "compiled body only",
            "market_data": {},
        },
    )

    assert captured["request"].full_user_prompt == (
        "execution context\n\n## Mentioned Target Outputs\n"
        f"- explore: {explore_artifact}\n\n"
        "compiled body"
    )


def test_run_internal_cycle_defaults_missing_expanded_prompt_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    engine = FakeEngine(["AAPL"])
    cycle_date = date(2024, 6, 17)
    cycle_ctx = {
        "prompt_report_slug": "prompt-42",
        "market_data": {"AAPL": {"close": Decimal("184.40")}},
    }

    monkeypatch.setattr(
        service, "_load_prompt_report", lambda prompt_report_slug: "# prompt report"
    )
    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: SimpleNamespace(orchestration_pattern_key="pattern"),
    )

    captured: dict[str, Any] = {}

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(report_content="", decisions=[])

    monkeypatch.setattr(
        service, "_build_langgraph_runner", lambda orchestration_pattern_key: FakeRunner()
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_update_run_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    class StoredReportEngine(FakeEngine):
        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            _ = (requested_cycle_date, analysis)
            return "report"

    engine = StoredReportEngine(["AAPL"])

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, engine),
        cycle_ctx=cycle_ctx,
    )

    request = captured["request"]
    assert request.authored_entry_prompt_body == ""
    assert request.compiled_entry_prompt_body == ""
    assert request.execution_context_body == ""
    assert request.full_user_prompt == ""


def test_run_internal_cycle_passes_expanded_prompt_bundle_to_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    runner = FakeRunner()
    cycle_date = date(2024, 6, 17)
    prompt_report = "# Prompt report\n\nPositions:\n- AAPL: 2 shares @ 184.40"
    captured: dict[str, Any] = {}

    def build_runner(orchestration_pattern_key: str) -> FakeRunner:
        captured["pattern_key"] = orchestration_pattern_key
        return runner

    class FakeEngine:
        def __init__(self) -> None:
            self.apply_calls: list[dict[str, Any]] = []
            self.record_calls: list[tuple[date, dict[str, dict[str, Decimal]]]] = []
            self.finalize_calls: list[dict[str, Any]] = []

        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            captured["stored_report"] = {
                "cycle_date": requested_cycle_date,
                "analysis": analysis,
            }
            return "langgraph_backtest_42_20240617"

        def apply_cycle_trades(
            self,
            *,
            cycle_date: date,
            decisions: list[Any],
            market_data: dict[str, dict[str, Decimal]],
            report_slug: str | None = None,
        ) -> list[dict[str, Any]]:
            self.apply_calls.append(
                {
                    "cycle_date": cycle_date,
                    "decisions": decisions,
                    "market_data": market_data,
                    "report_slug": report_slug,
                }
            )
            return []

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            self.record_calls.append((requested_cycle_date, market_data))
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            self.finalize_calls.append(
                {
                    "equity_points": equity_points,
                    "benchmark_history": benchmark_history,
                    "trade_log": trade_log,
                    "schedule": schedule,
                }
            )

        def _mark_failed(self, message: str) -> None:
            raise AssertionError(message)

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: cast(
            Backtest,
            SimpleNamespace(orchestration_pattern_key="seeded_internal_backtest_v1"),
        ),
    )
    monkeypatch.setattr(service, "_build_langgraph_runner", build_runner)
    monkeypatch.setattr(service, "_load_prompt_report", lambda prompt_report_slug: prompt_report)
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, FakeEngine()),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "market_data": {},
        },
    )

    assert captured["pattern_key"] == "seeded_internal_backtest_v1"

    request = runner.requests[0]
    assert request.backtest_id == 42
    assert request.cycle_date == cycle_date
    assert request.prompt_report_slug == "backtest_42_prompt_20240617"
    assert request.prompt_report == prompt_report
    assert request.authored_entry_prompt_body == ""
    assert request.compiled_entry_prompt_body == ""
    assert request.execution_context_body == ""
    assert request.full_user_prompt == ""


def test_dispatch_cycle_runs_internal_langgraph_analysis_without_webhook_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    captured: dict[str, Any] = {}

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(
                report_content="# LangGraph Analysis",
                decisions=[],
            )

    class FakeEngine:
        def __init__(self) -> None:
            self.apply_calls: list[dict[str, Any]] = []
            self.record_calls: list[tuple[date, dict[str, dict[str, Decimal]]]] = []
            self.finalize_calls: list[dict[str, Any]] = []

        def execute_cycle(self, requested_cycle_date: date) -> dict[str, Any]:
            return {
                "cancelled": False,
                "prompt_report_slug": "backtest_42_prompt_20240617",
                "market_data": {},
                "cycle_date": requested_cycle_date,
            }

        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            captured["stored_report"] = {
                "cycle_date": requested_cycle_date,
                "analysis": analysis,
            }
            return "langgraph_backtest_42_20240617"

        def apply_cycle_trades(
            self,
            *,
            cycle_date: date,
            decisions: list[Any],
            market_data: dict[str, dict[str, Decimal]],
            report_slug: str | None = None,
        ) -> list[dict[str, Any]]:
            self.apply_calls.append(
                {
                    "cycle_date": cycle_date,
                    "decisions": decisions,
                    "market_data": market_data,
                    "report_slug": report_slug,
                }
            )
            return []

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            self.record_calls.append((requested_cycle_date, market_data))
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            self.finalize_calls.append(
                {
                    "equity_points": equity_points,
                    "benchmark_history": benchmark_history,
                    "trade_log": trade_log,
                    "schedule": schedule,
                }
            )

        def _mark_failed(self, message: str) -> None:
            raise AssertionError(message)

    engine = FakeEngine()

    monkeypatch.setattr(
        service,
        "_build_engine",
        lambda backtest_id: cast(BacktestEngine, engine),
    )
    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: cast(
            Backtest,
            SimpleNamespace(orchestration_pattern_key="seeded_internal_backtest_v1"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_langgraph_runner",
        lambda orchestration_pattern_key: FakeRunner(),
    )
    monkeypatch.setattr(
        service,
        "_load_prompt_report",
        lambda prompt_report_slug: f"prompt content for {prompt_report_slug}",
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    monkeypatch.setattr(
        service,
        "_resolve_public_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("legacy webhook URL resolution should not be used")
        ),
    )

    service._dispatch_cycle(backtest_id=42, cycle_date=cycle_date)

    assert captured["request"].prompt_report_slug == "backtest_42_prompt_20240617"
    assert captured["request"].prompt_report == "prompt content for backtest_42_prompt_20240617"
    assert captured["stored_report"] == {
        "cycle_date": cycle_date,
        "analysis": "# LangGraph Analysis",
    }
    assert engine.apply_calls == [
        {
            "cycle_date": cycle_date,
            "decisions": [],
            "market_data": {},
            "report_slug": "langgraph_backtest_42_20240617",
        }
    ]
    assert engine.record_calls == [(cycle_date, {})]
    assert len(engine.finalize_calls) == 1


def test_run_internal_cycle_uses_stored_orchestration_pattern_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = build_service()
    cycle_date = date(2024, 6, 17)
    captured: dict[str, Any] = {}

    class FakeRunner:
        def run_cycle(self, request: Any) -> Any:
            return SimpleNamespace(report_content="# LangGraph Analysis", decisions=[])

    class FakeEngine:
        def _store_cycle_report(self, requested_cycle_date: date, analysis: str) -> str:
            _ = (requested_cycle_date, analysis)
            return "langgraph_backtest_42_20240617"

        def apply_cycle_trades(
            self,
            *,
            cycle_date: date,
            decisions: list[Any],
            market_data: dict[str, dict[str, Decimal]],
            report_slug: str | None = None,
        ) -> list[dict[str, Any]]:
            _ = (cycle_date, decisions, market_data, report_slug)
            return []

        def record_cycle_equity(
            self, requested_cycle_date: date, market_data: dict[str, dict[str, Decimal]]
        ) -> tuple[str, Decimal]:
            _ = market_data
            return requested_cycle_date.isoformat(), Decimal("100000.00")

        def finalize(
            self,
            *,
            equity_points: list[tuple[str, Decimal]],
            benchmark_history: dict[str, list[tuple[str, Decimal]]],
            trade_log: list[dict[str, Any]],
            schedule: list[date],
        ) -> None:
            _ = (equity_points, benchmark_history, trade_log, schedule)

    def build_runner(orchestration_pattern_key: str) -> Any:
        captured["pattern_key"] = orchestration_pattern_key
        return FakeRunner()

    monkeypatch.setattr(
        service,
        "_get_backtest_or_raise",
        lambda backtest_id: cast(
            Backtest,
            SimpleNamespace(orchestration_pattern_key="seeded_internal_backtest_v1"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_langgraph_runner",
        build_runner,
    )
    monkeypatch.setattr(
        service,
        "_load_prompt_report",
        lambda prompt_report_slug: f"prompt content for {prompt_report_slug}",
    )
    monkeypatch.setattr(
        service,
        "_load_run_state",
        lambda backtest_id: {
            "schedule": [cycle_date],
            "benchmark_history": {},
            "trade_log": [],
            "equity_points": [],
        },
    )
    monkeypatch.setattr(service, "_clear_cycle_status", lambda backtest_id: None)

    service._run_internal_cycle(
        backtest_id=42,
        cycle_date=cycle_date,
        engine=cast(BacktestEngine, FakeEngine()),
        cycle_ctx={
            "prompt_report_slug": "backtest_42_prompt_20240617",
            "market_data": {},
        },
    )

    assert captured["pattern_key"] == "seeded_internal_backtest_v1"


def test_handle_timeout_ignores_stale_timer_for_previous_cycle(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = create_backtest(
        session_factory,
        current_cycle_date=date(2024, 6, 18),
        current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value,
    )
    service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)

    service._handle_timeout(backtest_id, date(2024, 6, 17))

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == BacktestStatus.RUNNING.value
        assert backtest.current_cycle_status == BacktestStatus.AWAITING_CALLBACK.value
        assert backtest.current_cycle_date == date(2024, 6, 18)


def test_handle_timeout_fails_active_cycle_only(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = create_backtest(
        session_factory,
        current_cycle_date=date(2024, 6, 17),
        current_cycle_status=BacktestStatus.AWAITING_CALLBACK.value,
    )
    service = BacktestCycleService(cast(Session, SimpleNamespace()), session_factory)

    service._handle_timeout(backtest_id, date(2024, 6, 17))

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.status == BacktestStatus.FAILED.value
        assert backtest.current_cycle_status is None
        assert backtest.error_message == "Webhook callback timed out after 600s"
