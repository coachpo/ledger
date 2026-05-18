from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.orm import Session, sessionmaker

from app.repositories.workflow_package import WorkflowPackageRepository

_HASH_A = "a" * 64
_HASH_B = "b" * 64


class _PackagePayload(TypedDict):
    manifest_source: str
    manifest_hash: str
    package_definition: dict[str, Any]
    compiled_plan: dict[str, Any]
    compiled_hash: str
    validation_summary: dict[str, Any]


def _package_payload(package_key: str = "market_review") -> _PackagePayload:
    return {
        "manifest_source": "apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n",
        "manifest_hash": _HASH_A,
        "package_definition": {
            "apiVersion": "signaldeck.workflowPackage/v1",
            "kind": "WorkflowPackage",
            "metadata": {"key": package_key, "name": "Market Review"},
            "spec": {"agents": [{"key": "review_agent"}], "workflows": []},
        },
        "compiled_plan": {
            "packageKey": package_key,
            "agents": [{"key": "review_agent"}],
            "workflows": [{"key": "primary_workflow"}],
        },
        "compiled_hash": _HASH_B,
        "validation_summary": {"diagnostics": []},
    }


def _create_current_package(session: Session, key: str = "market_review"):
    repository = WorkflowPackageRepository(session)
    package = repository.create_package(
        key=key,
        name="Market Review",
        description="Current package",
        status="draft",
        **_package_payload(key),
    )
    session.commit()
    return package


def test_workflow_package_repository_creates_current_package_artifact(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = WorkflowPackageRepository(session)
        package = repository.create_package(
            key="market_review",
            name="Market Review",
            description="Current package",
            status="draft",
            **_package_payload(),
        )
        session.commit()

        stored = repository.get_by_key("market_review")

        assert stored is not None
        assert stored.id == package.id
        assert stored.manifest_source == _package_payload()["manifest_source"]
        assert stored.manifest_hash == _HASH_A
        assert stored.compiled_hash == _HASH_B
        assert stored.package_definition["metadata"]["key"] == "market_review"
        assert stored.compiled_plan["workflows"][0]["key"] == "primary_workflow"
        assert stored.validation_summary == {"diagnostics": []}


def test_workflow_package_repository_lists_and_updates_current_packages(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _create_current_package(session)
        repository = WorkflowPackageRepository(session)

        repository.update_package(package, name="Updated Market Review", status="active")
        session.commit()

        assert repository.get_by_key("market_review") is not None
        assert ("market_review", "active") in [
            (item.key, item.status) for item in repository.list_packages()
        ]
        assert [(item.key, item.status) for item in repository.list_packages(status="draft")] == []


def test_workflow_package_repository_replaces_current_artifact_in_place(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package = _create_current_package(session)
        repository = WorkflowPackageRepository(session)
        replacement = _package_payload()
        replacement["manifest_source"] = (
            "apiVersion: signaldeck.workflowPackage/v1\n"
            "kind: WorkflowPackage\n"
            "metadata:\n"
            "  key: market_review\n"
        )
        replacement["manifest_hash"] = _HASH_B
        replacement["compiled_hash"] = _HASH_A
        replacement["validation_summary"] = {"diagnostics": [{"severity": "warning"}]}

        repository.update_package(package, **replacement)
        session.commit()

        stored = repository.get_by_key("market_review")

        assert stored is not None
        assert stored.id == package.id
        assert stored.manifest_source == replacement["manifest_source"]
        assert stored.manifest_hash == _HASH_B
        assert stored.compiled_hash == _HASH_A
        assert stored.validation_summary == {"diagnostics": [{"severity": "warning"}]}
