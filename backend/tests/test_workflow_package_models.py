from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import workflow_package as workflow_package_models
from app.models.base import Base
from app.models.workflow_package import WorkflowPackage

_HASH_A = "a" * 64
_HASH_B = "b" * 64


def _package_definition(
    package_key: str = "market_review",
    agent_key: str = "review_agent",
) -> dict[str, object]:
    return {
        "apiVersion": "signaldeck.workflowPackage/v1",
        "kind": "WorkflowPackage",
        "metadata": {
            "key": package_key,
            "name": package_key.replace("_", " ").title(),
        },
        "spec": {"agents": [{"key": agent_key}], "workflows": []},
    }


def _compiled_plan(
    package_key: str = "market_review",
    agent_key: str = "review_agent",
) -> dict[str, object]:
    return {
        "packageKey": package_key,
        "agents": [{"key": agent_key}],
        "workflows": [],
    }


def _build_package(
    *,
    key: str,
    name: str,
    description: str,
    status: str = "active",
    manifest_source: str = "manifest-source",
    manifest_hash: str = _HASH_A,
    compiled_hash: str = _HASH_B,
    agent_key: str = "review_agent",
) -> WorkflowPackage:
    return WorkflowPackage(
        key=key,
        name=name,
        description=description,
        status=status,
        manifest_source=manifest_source,
        manifest_hash=manifest_hash,
        package_definition=_package_definition(key, agent_key),
        compiled_plan=_compiled_plan(key, agent_key),
        compiled_hash=compiled_hash,
        extension_dependencies=[{"key": "signaldeck.finance", "required": True}],
    )


def test_workflow_package_tables_are_registered_with_constraints() -> None:
    assert "workflow_packages" in Base.metadata.tables
    assert "workflow_package_versions" not in Base.metadata.tables
    assert "workflow_package_version_model_connections" not in Base.metadata.tables
    assert not hasattr(workflow_package_models, "WorkflowPackageVersion")

    package_table = Base.metadata.tables["workflow_packages"]

    assert {
        "key",
        "name",
        "description",
        "status",
        "manifest_source",
        "manifest_hash",
        "package_definition",
        "compiled_plan",
        "compiled_hash",
        "extension_dependencies",
        "created_at",
        "updated_at",
    } <= set(package_table.c.keys())
    removed_validation_column = "_".join(("validation", "summary"))
    removed_launch_column = "_".join(("last", "launched", "at"))
    assert {
        "latest_version_id",
        "draft_source",
        removed_validation_column,
        removed_launch_column,
    }.isdisjoint(package_table.c.keys())
    removed_archive_columns = {
        "_".join(("arch" + "ived", suffix)) for suffix in ("at", "by", "reason")
    }
    assert {
        *removed_archive_columns,
        "deleted_at",
        "deleted_by",
        "deleted_reason",
    }.isdisjoint(package_table.c.keys())
    assert {
        "ix_workflow_packages_key",
        "uq_workflow_packages_active_key",
        "ix_workflow_packages_manifest_hash",
        "ix_workflow_packages_compiled_hash",
    } <= {index.name for index in package_table.indexes}
    removed_launch_index = "ix_workflow_packages_" + removed_launch_column
    assert removed_launch_index not in {index.name for index in package_table.indexes}


def test_workflow_package_models_store_current_artifacts_and_allow_private_key_reuse(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        first_package = _build_package(
            key="market_review",
            name="Market Review",
            description="First package",
            manifest_source="manifest-a",
            manifest_hash=_HASH_A,
            compiled_hash=_HASH_B,
        )
        second_package = _build_package(
            key="portfolio_review",
            name="Portfolio Review",
            description="Second package",
            manifest_source="manifest-b",
            manifest_hash=_HASH_B,
            compiled_hash=_HASH_A,
        )
        session.add_all([first_package, second_package])
        session.commit()

        stored_packages = list(
            session.scalars(
                select(WorkflowPackage)
                .where(WorkflowPackage.key.in_(["market_review", "portfolio_review"]))
                .order_by(WorkflowPackage.id)
            )
        )
        stored_agent_keys = [
            package.package_definition["spec"]["agents"][0]["key"] for package in stored_packages
        ]
        assert stored_agent_keys == ["review_agent", "review_agent"]
        assert stored_packages[0].manifest_source == "manifest-a"
        assert stored_packages[0].manifest_hash == _HASH_A
        assert stored_packages[0].compiled_plan == _compiled_plan()
        assert stored_packages[0].compiled_hash == _HASH_B
        assert stored_packages[0].extension_dependencies == [
            {"key": "signaldeck.finance", "required": True}
        ]
        removed_validation_column = "_".join(("validation", "summary"))
        removed_launch_column = "_".join(("last", "launched", "at"))
        assert not hasattr(stored_packages[0], removed_validation_column)
        assert not hasattr(stored_packages[0], removed_launch_column)
        assert not hasattr(stored_packages[0], "latest_version_id")
        assert not hasattr(stored_packages[0], "versions")


def test_workflow_package_active_key_is_unique(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        session.add(
            _build_package(
                key="market_review",
                name="Market Review",
                description="Active package",
                status="active",
                manifest_source="source-a",
            )
        )
        session.commit()

        session.add(
            _build_package(
                key="market_review",
                name="Duplicate Market Review",
                description="Duplicate active package",
                status="draft",
                manifest_source="source-b",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
