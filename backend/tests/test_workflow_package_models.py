from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _package_definition(agent_key: str = "review_agent") -> dict[str, object]:
    return {
        "apiVersion": "ledger.workflowPackage/v1",
        "kind": "WorkflowPackage",
        "metadata": {"key": "market_review", "name": "Market Review"},
        "spec": {"agents": [{"key": agent_key}], "workflows": []},
    }


def _compiled_plan(agent_key: str = "review_agent") -> dict[str, object]:
    return {"packageKey": "market_review", "agents": [{"key": agent_key}], "workflows": []}


def test_workflow_package_tables_are_registered_with_constraints() -> None:
    assert {"workflow_packages", "workflow_package_versions"} <= set(Base.metadata.tables)

    package_table = Base.metadata.tables["workflow_packages"]
    version_table = Base.metadata.tables["workflow_package_versions"]

    assert {
        "key",
        "name",
        "description",
        "status",
        "latest_version_id",
        "draft_source",
        "archived_at",
        "archived_by",
        "archived_reason",
        "deleted_at",
        "deleted_by",
        "deleted_reason",
        "created_at",
        "updated_at",
    } <= set(package_table.c.keys())
    assert {
        "package_id",
        "version",
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
        "validation_summary",
        "created_at",
        "launched_at",
    } <= set(version_table.c.keys())
    assert {"ix_workflow_packages_key", "uq_workflow_packages_active_key"} <= {
        index.name for index in package_table.indexes
    }
    assert "uq_workflow_package_versions_package_version" in {
        constraint.name for constraint in version_table.constraints
    }


def test_workflow_package_models_store_versions_and_allow_private_key_reuse(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first_package = WorkflowPackage(
            key="market_review",
            name="Market Review",
            description="First package",
            status="active",
            draft_source="source-a",
        )
        second_package = WorkflowPackage(
            key="portfolio_review",
            name="Portfolio Review",
            description="Second package",
            status="active",
            draft_source="source-b",
        )
        session.add_all([first_package, second_package])
        session.flush()
        first_version = WorkflowPackageVersion(
            package_id=first_package.id,
            version=1,
            manifest_source="manifest-a",
            manifest_hash=_HASH_A,
            package_definition=_package_definition(),
            compiled_plan=_compiled_plan(),
            compiled_hash=_HASH_B,
            validation_summary={"diagnostics": []},
        )
        second_version = WorkflowPackageVersion(
            package_id=second_package.id,
            version=1,
            manifest_source="manifest-b",
            manifest_hash=_HASH_B,
            package_definition=_package_definition(),
            compiled_plan=_compiled_plan(),
            compiled_hash=_HASH_A,
            validation_summary={"diagnostics": []},
        )
        session.add_all([first_version, second_version])
        session.flush()
        first_package.latest_version_id = first_version.id
        second_package.latest_version_id = second_version.id
        session.commit()

        stored_versions = list(
            session.scalars(select(WorkflowPackageVersion).order_by(WorkflowPackageVersion.id))
        )
        stored_agent_keys = [
            version.package_definition["spec"]["agents"][0]["key"] for version in stored_versions
        ]
        assert stored_agent_keys == ["review_agent", "review_agent"]
        assert first_package.latest_version_id == first_version.id


def test_workflow_package_active_key_is_unique(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            WorkflowPackage(
                key="market_review",
                name="Market Review",
                description="Active package",
                status="active",
                draft_source="source-a",
            )
        )
        session.commit()

        session.add(
            WorkflowPackage(
                key="market_review",
                name="Duplicate Market Review",
                description="Duplicate active package",
                status="draft",
                draft_source="source-b",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
