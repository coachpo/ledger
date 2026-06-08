from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agents import get_default_tool_catalog
from app.core.errors import ApiError
from app.models.portfolio import Portfolio
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.models.workflow_package import WorkflowPackage
from app.schemas.model_connection import ModelConnectionCreate
from app.schemas.portfolio import PortfolioCreate
from app.schemas.text_template import TextTemplateCreate
from app.schemas.workflow_package import (
    WorkflowPackageImportRequest,
    WorkflowPackageManifestRequest,
)
from app.services.model_connection_service import ModelConnectionService
from app.services.portfolio_service import PortfolioService
from app.services.report_service import ReportService
from app.services.text_template_service import TextTemplateService
from app.services.workflow_package_service import WorkflowPackageService

_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "tradingagents_advisory_research.yaml"
)


def _package_source() -> str:
    return _FIXTURE.read_text()


def _race_once_on_commit(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    winner: Callable[[], None],
) -> None:
    original_commit = session.commit
    raced = False

    def racing_commit() -> None:
        nonlocal raced
        if not raced:
            raced = True
            winner()
        original_commit()

    monkeypatch.setattr(session, "commit", racing_commit)


def _assert_session_is_usable(session: Session) -> None:
    assert session.scalar(select(1)) == 1


def _model_connection_payload(key: str) -> ModelConnectionCreate:
    return ModelConnectionCreate.model_validate(
        {
            "key": key,
            "name": "Race Model",
            "description": "Race test model connection.",
            "baseUrl": "https://provider.example.test",
            "modelId": "gpt-5.5-mini",
            "reasoningEffort": "medium",
            "protocolProfile": "openai_responses",
            "timeoutSeconds": 60,
            "apiKey": "test-api-key",
        }
    )


def test_portfolio_create_translates_commit_time_slug_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = PortfolioService(session)

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                winner_session.add(
                    Portfolio(
                        name="Winner Portfolio",
                        slug="race_portfolio",
                        description=None,
                        base_currency="USD",
                    )
                )
                winner_session.commit()

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_portfolio(
                PortfolioCreate(
                    name="Race Portfolio",
                    slug="race_portfolio",
                    description=None,
                    base_currency="USD",
                )
            )

        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert excinfo.value.code == "duplicate_portfolio_slug"
        _assert_session_is_usable(session)


def test_template_create_translates_commit_time_name_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = TextTemplateService(session)

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                winner_session.add(TextTemplate(name="Race Template", content="# Winner"))
                winner_session.commit()

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_template(TextTemplateCreate(name="Race Template", content="# Loser"))

        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert excinfo.value.code == "duplicate_template_name"
        _assert_session_is_usable(session)


def test_report_external_create_translates_commit_time_slug_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = ReportService(session)

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                winner_session.add(
                    Report(
                        name="Winner Report",
                        slug="race_report",
                        source="external",
                        content="# Winner",
                        metadata_={},
                    )
                )
                winner_session.commit()

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_external_report(
                content="# Loser",
                name="Loser Report",
                slug="race_report",
            )

        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.code == "slug_conflict"
        _assert_session_is_usable(session)


def test_model_connection_create_translates_commit_time_key_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = ModelConnectionService(session)
        payload = _model_connection_payload("race_model")

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                _ = ModelConnectionService(winner_session).create_connection(
                    _model_connection_payload("race_model")
                )

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_connection(payload)

        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.code == "model_connection_duplicate_key"
        _assert_session_is_usable(session)


def test_workflow_package_create_translates_commit_time_key_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = WorkflowPackageService(session, tool_catalog=get_default_tool_catalog())
        payload = WorkflowPackageManifestRequest(manifest_source=_package_source())

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                _ = WorkflowPackageService(
                    winner_session,
                    tool_catalog=get_default_tool_catalog(),
                ).create_package(payload)

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.create_package(payload)

        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.code == "workflow_package_duplicate_key"
        assert session.scalar(select(WorkflowPackage.id)) is not None
        _assert_session_is_usable(session)


def test_workflow_package_import_translates_commit_time_key_conflict(
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with session_factory() as session:
        service = WorkflowPackageService(session, tool_catalog=get_default_tool_catalog())
        create_payload = WorkflowPackageManifestRequest(manifest_source=_package_source())
        import_payload = WorkflowPackageImportRequest(manifest_source=_package_source())

        def insert_duplicate() -> None:
            with session_factory() as winner_session:
                _ = WorkflowPackageService(
                    winner_session,
                    tool_catalog=get_default_tool_catalog(),
                ).create_package(create_payload)

        _race_once_on_commit(monkeypatch, session, insert_duplicate)

        with pytest.raises(ApiError) as excinfo:
            _ = service.import_package(import_payload)

        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.code == "workflow_package_import_conflict"
        assert session.scalar(select(WorkflowPackage.id)) is not None
        _assert_session_is_usable(session)
