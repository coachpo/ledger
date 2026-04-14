from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from app.models.backtest import Backtest
from app.models.balance import Balance
from app.models.orchestration_character import OrchestrationCharacter
from app.models.orchestration_role import OrchestrationRole
from app.models.portfolio import Portfolio
from app.models.report import Report
from app.models.text_template import TextTemplate
from app.services.backtest_runtime_adapter import BacktestRuntimeAdapter
from app.services.persona_projection_service import PersonaProjectionService


def _create_backtest(
    session: Session,
    *,
    name: str,
    orchestration_pattern_key: str,
) -> Backtest:
    portfolio = Portfolio(name=f"{name} Portfolio", slug=f"{name}_portfolio", base_currency="USD")
    session.add(portfolio)
    session.flush()

    balance = Balance(
        portfolio_id=portfolio.id,
        label="Cash",
        operation_type="DEPOSIT",
        amount=Decimal("1000.00"),
        currency="USD",
    )
    template = TextTemplate(name=f"{name} Template", content="# Runtime Mention Test")
    session.add_all([balance, template])
    session.flush()

    backtest = Backtest(
        portfolio_id=portfolio.id,
        deposit_balance_id=balance.id,
        name=name,
        orchestration_pattern_key=orchestration_pattern_key,
        workflow_spec_key=orchestration_pattern_key,
        workflow_spec_version=1,
        execution_owner="runtime_v2",
        status="RUNNING",
        frequency="DAILY",
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 31),
        total_cycles=5,
        completed_cycles=0,
        template_id=template.id,
        webhook_url="internal://ledger",
        webhook_timeout=600,
        price_mode="CLOSING_PRICE",
        commission_mode="ZERO",
        commission_value=Decimal("0"),
        benchmark_symbols=["^GSPC"],
    )
    session.add(backtest)
    session.flush()
    return backtest


def _create_prompt_report(
    session: Session, *, backtest_id: int, cycle_date: date, slug: str
) -> None:
    session.add(
        Report(
            name=slug,
            slug=slug,
            source="external",
            content="# Prompt\n\nRuntime mention prompt report.",
            metadata_={
                "tags": ["backtest", f"backtest_{backtest_id}", "prompt"],
                "analysis": {
                    "backtestId": backtest_id,
                    "cycleDate": cycle_date.isoformat(),
                    "reviewType": "backtest_prompt",
                },
            },
        )
    )


def _create_projected_character(session: Session, *, handle: str) -> OrchestrationCharacter:
    role = OrchestrationRole(
        key=f"{handle}_role",
        name=f"{handle.title()} Role",
        description=f"{handle.title()} role",
        system_prompt=f"{handle.title()} system prompt",
        capability_bundle_keys=[],
        enabled=True,
    )
    session.add(role)
    session.flush()
    character = OrchestrationCharacter(
        handle=handle,
        display_name=handle.title(),
        description=f"{handle.title()} character",
        role_id=role.id,
        prompt_append=f"{handle.title()} guidance",
        capability_bundle_keys=[],
        enabled=True,
    )
    session.add(character)
    session.flush()
    PersonaProjectionService(session).project_character(character, role=role)
    session.flush()
    return character


def test_runtime_artifacts_scan_authored_prompt_only_for_mentions(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 17)
    prompt_slug = "runtime_mentions_authored_only"

    with session_factory() as session:
        backtest = _create_backtest(
            session,
            name="runtime_mentions_authored_only",
            orchestration_pattern_key="seeded_internal_backtest_v1",
        )
        _create_prompt_report(
            session,
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            slug=prompt_slug,
        )
        session.commit()

        adapter = BacktestRuntimeAdapter(session, session_factory)
        prepared = adapter.runtime_service.prepare_run(
            adapter._build_runtime_payload(
                backtest=backtest,
                cycle_date=cycle_date,
                cycle_ctx={
                    "prompt_report_slug": prompt_slug,
                    "authored_entry_prompt_body": "",
                    "compiled_entry_prompt_body": "Compiled body mentions @librarian.",
                    "execution_context_body": "Execution context mentions @explore.",
                    "full_user_prompt": "Compiled + context mentions only.",
                    "market_data": {},
                },
            )
        )
        artifact = adapter.runtime_service.get_artifact(prepared.run_id)

    assert artifact.raw_mention_handles == []
    assert artifact.resolved_mentions == []
    assert artifact.resolved_builtin_versions == []
    assert artifact.resolved_role_versions == []
    assert artifact.resolved_character_versions == []


def test_runtime_artifacts_persist_native_mention_compilation_shape(
    session_factory: sessionmaker[Session],
) -> None:
    cycle_date = date(2024, 6, 18)
    prompt_slug = "runtime_mentions_native_shape"

    with session_factory() as session:
        backtest = _create_backtest(
            session,
            name="runtime_mentions_native_shape",
            orchestration_pattern_key="analyst_reviewer_v1",
        )
        character = _create_projected_character(session, handle="analyst")
        _create_prompt_report(
            session,
            backtest_id=backtest.id,
            cycle_date=cycle_date,
            slug=prompt_slug,
        )
        session.commit()

        adapter = BacktestRuntimeAdapter(session, session_factory)
        payload = adapter._build_runtime_payload(
            backtest=backtest,
            cycle_date=cycle_date,
            cycle_ctx={
                "prompt_report_slug": prompt_slug,
                "authored_entry_prompt_body": (
                    "Ask @librarian and @analyst before @librarian decides."
                ),
                "compiled_entry_prompt_body": "Compiled body.",
                "execution_context_body": "Execution context.",
                "full_user_prompt": "Runtime handoff.",
                "market_data": {},
            },
        )
        prepared = adapter.runtime_service.prepare_run(payload)
        artifact = adapter.runtime_service.get_artifact(prepared.run_id)
        native_mentions = artifact.model_dump(by_alias=True)["resolvedMentions"]
        persona_ref_keys = {
            (item["personaProfileKey"], item["personaProfileVersion"])
            for item in artifact.model_dump(by_alias=True)["resolvedPersonaProfileRefs"]
        }
        payload_dump = payload.model_dump(by_alias=True)
        native_role_versions = json.loads(payload.inputs["resolved_role_versions_json"])
        native_character_versions = json.loads(payload.inputs["resolved_character_versions_json"])

    assert artifact.raw_mention_handles == ["librarian", "analyst", "librarian"]
    assert [item["sourceHandle"] for item in native_mentions] == ["librarian", "analyst"]
    assert all("handle" not in item for item in native_mentions)
    assert native_mentions[0]["personaProfileKey"] == "builtin:librarian"
    assert native_mentions[0]["personaProfileVersion"] == 1
    assert native_mentions[1]["personaProfileKey"] == "imported.character.analyst"
    assert native_mentions[1]["legacyRoleId"] == character.role_id
    assert native_mentions[1]["legacyCharacterId"] == character.id
    assert ("builtin:librarian", 1) in persona_ref_keys
    assert (
        "imported.character.analyst",
        native_mentions[1]["personaProfileVersion"],
    ) in persona_ref_keys
    assert any(
        item["personaProfileKey"] == "imported.role.analyst_role"
        for item in payload_dump["personaProfileRefs"]
    )
    assert native_role_versions == [
        {
            "canonical_target_id": "role:analyst_role",
            "role_id": character.role_id,
            "version": native_mentions[1]["legacyRoleVersion"],
        }
    ]
    assert native_character_versions == [
        {
            "canonical_target_id": "character:analyst",
            "character_id": character.id,
            "version": native_mentions[1]["legacyCharacterVersion"],
        }
    ]
