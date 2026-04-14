from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.core.formatting import utcnow
from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.text_template import TextTemplate
from app.schemas.backtest import BacktestExecutionOwner, BacktestLaunchMode
from app.services.backtest_classification_service import (
    BacktestClassificationService,
    BacktestManifestClassification,
)


def _seed_backtest(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    status: str = "COMPLETED",
    orchestration_pattern_key: str = "seeded_internal_backtest_v1",
    webhook_url: str = "http://localhost:5678/webhook/historical",
    launch_mode: str | None = None,
    workflow_spec_key: str | None = None,
    workflow_spec_version: int | None = None,
    execution_owner: str | None = None,
    launch_mode_classified_at: datetime | None = None,
    launch_mode_classified_by: str | None = None,
    launch_mode_classification_note: str | None = None,
) -> int:
    with session_factory() as session:
        portfolio = Portfolio(
            name=f"{name} Portfolio", slug=f"{name}_portfolio", base_currency="USD"
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
        template = TextTemplate(name=f"{name} Template", content="# Classification")
        session.add_all([balance, template])
        session.flush()

        backtest = Backtest(
            portfolio_id=portfolio.id,
            deposit_balance_id=balance.id,
            name=name,
            orchestration_pattern_key=orchestration_pattern_key,
            launch_mode=launch_mode,
            workflow_spec_key=workflow_spec_key,
            workflow_spec_version=workflow_spec_version,
            execution_owner=execution_owner,
            status=status,
            frequency="DAILY",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 31),
            total_cycles=5,
            completed_cycles=5 if status == "COMPLETED" else 1,
            template_id=template.id,
            webhook_url=webhook_url,
            webhook_timeout=600,
            price_mode="CLOSING_PRICE",
            commission_mode="ZERO",
            commission_value=Decimal("0"),
            benchmark_symbols=["^GSPC"],
            launch_mode_classified_at=launch_mode_classified_at,
            launch_mode_classified_by=launch_mode_classified_by,
            launch_mode_classification_note=launch_mode_classification_note,
        )
        session.add(backtest)
        session.commit()
        return backtest.id


def test_manifest_classification_pins_seeded_internal_backtest_by_backtest_id(
    session_factory: sessionmaker[Session],
) -> None:
    targeted_id = _seed_backtest(session_factory, name="targeted")
    untouched_id = _seed_backtest(session_factory, name="untouched")

    with session_factory() as session:
        service = BacktestClassificationService(session)
        classified = service.classify_backtests_from_manifest(
            [
                BacktestManifestClassification(
                    backtest_id=targeted_id,
                    launch_mode=BacktestLaunchMode.INTERNAL,
                    execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                    classified_by="migration-script",
                    classification_note="operator reviewed",
                )
            ]
        )
        assert [backtest.id for backtest in classified] == [targeted_id]

    with session_factory() as session:
        targeted = session.get(Backtest, targeted_id)
        untouched = session.get(Backtest, untouched_id)
        assert targeted is not None
        assert targeted.launch_mode == "internal"
        assert targeted.workflow_spec_key == "seeded_internal_backtest_v1"
        assert targeted.workflow_spec_version == 1
        assert targeted.execution_owner == "runtime_v2"
        assert targeted.launch_mode_classified_at is not None
        assert targeted.launch_mode_classified_by == "migration-script"
        assert targeted.launch_mode_classification_note == "operator reviewed"

        assert untouched is not None
        assert untouched.launch_mode is None
        assert untouched.workflow_spec_key is None
        assert untouched.workflow_spec_version is None
        assert untouched.execution_owner is None


def test_manifest_classification_is_idempotent_for_matching_existing_routing(
    session_factory: sessionmaker[Session],
) -> None:
    classified_at = utcnow()
    backtest_id = _seed_backtest(
        session_factory,
        name="idempotent",
        launch_mode="internal",
        workflow_spec_key="seeded_internal_backtest_v1",
        workflow_spec_version=1,
        execution_owner="runtime_v2",
        launch_mode_classified_at=classified_at,
        launch_mode_classified_by="original-classifier",
        launch_mode_classification_note="kept original",
    )

    with session_factory() as session:
        service = BacktestClassificationService(session)
        service.classify_backtests_from_manifest(
            [
                BacktestManifestClassification(
                    backtest_id=backtest_id,
                    launch_mode=BacktestLaunchMode.INTERNAL,
                    execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                    classified_by="different-actor",
                    classification_note="different note",
                )
            ]
        )

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.launch_mode == "internal"
        assert backtest.workflow_spec_key == "seeded_internal_backtest_v1"
        assert backtest.workflow_spec_version == 1
        assert backtest.execution_owner == "runtime_v2"
        assert backtest.launch_mode_classified_at == classified_at
        assert backtest.launch_mode_classified_by == "original-classifier"
        assert backtest.launch_mode_classification_note == "kept original"


def test_manifest_classification_rejects_repinning_already_classified_backtest(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = _seed_backtest(
        session_factory,
        name="repin_rejected",
        launch_mode="internal",
        workflow_spec_key="seeded_internal_backtest_v1",
        workflow_spec_version=1,
        execution_owner="legacy_path",
        launch_mode_classified_at=utcnow(),
        launch_mode_classified_by="migration-script",
    )

    with session_factory() as session:
        service = BacktestClassificationService(session)
        with pytest.raises(ApiError, match="already pinned") as exc:
            service.classify_backtests_from_manifest(
                [
                    BacktestManifestClassification(
                        backtest_id=backtest_id,
                        launch_mode=BacktestLaunchMode.INTERNAL,
                        execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                        classified_by="migration-script",
                    )
                ]
            )
        assert exc.value.code == "backtest_classification_conflict"


def test_manifest_classification_rejects_selector_owner_mismatch_for_legacy_callback(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = _seed_backtest(session_factory, name="legacy_mismatch")

    with session_factory() as session:
        service = BacktestClassificationService(session)
        with pytest.raises(ApiError, match="must remain on legacy_path") as exc:
            service.classify_backtests_from_manifest(
                [
                    BacktestManifestClassification(
                        backtest_id=backtest_id,
                        launch_mode=BacktestLaunchMode.LEGACY_CALLBACK,
                        execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                        classified_by="migration-script",
                    )
                ]
            )
        assert exc.value.code == "invalid_backtest_execution_owner"


def test_manifest_classification_rejects_runtime_v2_for_unknown_workflow_selector(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = _seed_backtest(
        session_factory,
        name="unknown_selector",
        orchestration_pattern_key="custom_legacy_pattern_v9",
    )

    with session_factory() as session:
        service = BacktestClassificationService(session)
        with pytest.raises(
            ApiError,
            match="rollback-compatible seeded workflow pin",
        ) as exc:
            service.classify_backtests_from_manifest(
                [
                    BacktestManifestClassification(
                        backtest_id=backtest_id,
                        launch_mode=BacktestLaunchMode.INTERNAL,
                        execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                        classified_by="migration-script",
                    )
                ]
            )
        assert exc.value.code == "invalid_backtest_execution_owner"


def test_manifest_classification_rejects_rehoming_running_backtest_to_runtime_v2(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = _seed_backtest(session_factory, name="running_rehome", status="RUNNING")

    with session_factory() as session:
        service = BacktestClassificationService(session)
        with pytest.raises(ApiError, match="cannot be re-homed") as exc:
            service.classify_backtests_from_manifest(
                [
                    BacktestManifestClassification(
                        backtest_id=backtest_id,
                        launch_mode=BacktestLaunchMode.INTERNAL,
                        execution_owner=BacktestExecutionOwner.RUNTIME_V2,
                        classified_by="migration-script",
                    )
                ]
            )
        assert exc.value.code == "backtest_classification_rehome_rejected"


def test_historical_rows_stay_unclassified_without_manifest_even_with_webhook_url(
    session_factory: sessionmaker[Session],
) -> None:
    backtest_id = _seed_backtest(
        session_factory,
        name="webhook_only",
        webhook_url="http://localhost:9876/webhook/runtime",
    )

    with session_factory() as session:
        backtest = session.get(Backtest, backtest_id)
        assert backtest is not None
        assert backtest.webhook_url == "http://localhost:9876/webhook/runtime"
        assert backtest.launch_mode is None
        assert backtest.workflow_spec_key is None
        assert backtest.workflow_spec_version is None
        assert backtest.execution_owner is None
