from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.agent_spec import AgentSpec
from app.models.base import Base
from app.models.runtime_run import RuntimeRun

RUNTIME_V2_TABLE_NAMES = {
    "agent_specs",
    "workflow_specs",
    "persona_profiles",
    "capability_registry_entries",
    "runtime_runs",
    "runtime_trace_events",
    "runtime_approvals",
    "runtime_checkpoints",
    "runtime_run_artifacts",
    "persona_projection_events",
}


def _build_agent_spec(*, key: str, version: int, status: str) -> AgentSpec:
    return AgentSpec(
        key=key,
        version=version,
        origin="managed",
        status=status,
        name=f"{key}-{version}",
        instructions="Follow the workflow.",
        model_policy={"model": "gpt-5.4-mini"},
        final_output_contract={"kind": "text", "schema": None, "description": "Result"},
        default_capability_bundle_keys=[],
        default_persona_profile_keys=[],
    )


def _build_runtime_run(*, attempt_number: int, status: str) -> RuntimeRun:
    return RuntimeRun(
        caller_type="studio",
        caller_id=42,
        execution_kind="workflow",
        workflow_spec_key="alpha_workflow",
        workflow_spec_version=1,
        caller_scope_key="studio-session-42",
        caller_identity_key=None,
        attempt_number=attempt_number,
        status=status,
        input_hash=f"{attempt_number}" * 64,
        output_hash=None,
        retention_class="persistent",
    )


def test_runtime_v2_tables_are_registered_on_metadata() -> None:
    assert RUNTIME_V2_TABLE_NAMES <= set(Base.metadata.tables)

    agent_spec_table = Base.metadata.tables["agent_specs"]
    runtime_runs_table = Base.metadata.tables["runtime_runs"]

    assert {
        "uq_agent_specs_active_key",
        "uq_agent_specs_draft_key",
    } <= {index.name for index in agent_spec_table.indexes}
    assert "uq_runtime_runs_active_backtest_cycle" not in {
        index.name for index in runtime_runs_table.indexes
    }
    assert "uq_runtime_runs_caller_scope_attempt" in {
        constraint.name for constraint in runtime_runs_table.constraints if constraint.name
    }


def test_agent_specs_enforce_single_active_and_single_draft_versions(session_factory) -> None:
    with session_factory() as session:
        session.add(_build_agent_spec(key="allocation_agent", version=1, status="ACTIVE"))
        session.commit()

        session.add(_build_agent_spec(key="allocation_agent", version=2, status="ACTIVE"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_build_agent_spec(key="allocation_agent", version=2, status="DRAFT"))
        session.commit()

        session.add(_build_agent_spec(key="allocation_agent", version=3, status="DRAFT"))
        with pytest.raises(IntegrityError):
            session.commit()


def test_runtime_runs_enforce_unique_attempts_per_caller_scope(session_factory) -> None:
    with session_factory() as session:
        session.add(_build_runtime_run(attempt_number=1, status="RUNNING"))
        session.commit()

        session.add(_build_runtime_run(attempt_number=1, status="FAILED"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_build_runtime_run(attempt_number=2, status="WAITING_APPROVAL"))
        session.commit()
