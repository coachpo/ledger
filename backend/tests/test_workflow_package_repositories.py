from __future__ import annotations

from typing import Any, TypedDict

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.repositories.workflow_package import WorkflowPackageRepository

_HASH_A = "a" * 64
_HASH_B = "b" * 64


class _VersionPayload(TypedDict):
    manifest_source: str
    manifest_hash: str
    package_definition: dict[str, Any]
    compiled_plan: dict[str, Any]
    compiled_hash: str
    validation_summary: dict[str, Any]


def _version_payload(package_key: str = "market_review") -> _VersionPayload:
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


def _create_package_with_version(session: Session, key: str = "market_review"):
    repository = WorkflowPackageRepository(session)
    package = repository.create_package(
        key=key,
        name="Market Review",
        description="Draft package",
        status="draft",
        draft_source="draft manifest",
    )
    session.flush()
    version = repository.create_version(package, **_version_payload(key))
    session.commit()
    return package, version


def test_workflow_package_repository_creates_versions_and_resolves_latest(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = WorkflowPackageRepository(session)
        package = repository.create_package(
            key="market_review",
            name="Market Review",
            description="Draft package",
            draft_source="draft manifest",
        )
        session.flush()
        first_version = repository.create_version(package, **_version_payload())
        second_payload = _version_payload()
        second_payload["manifest_hash"] = _HASH_B
        second_payload["compiled_hash"] = _HASH_A
        second_version = repository.create_version(package, **second_payload)
        session.commit()

        assert first_version.version == 1
        assert second_version.version == 2
        assert package.latest_version_id == second_version.id
        assert repository.get_by_key("market_review") is not None
        latest_version = repository.get_latest_version(package.id)
        stored_first_version = repository.get_version(package.id, 1)
        assert latest_version is not None
        assert stored_first_version is not None
        assert latest_version.id == second_version.id
        assert [version.version for version in repository.list_versions(package.id)] == [2, 1]
        assert stored_first_version.id == first_version.id


def test_workflow_package_repository_lists_and_updates_packages(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        package, _version = _create_package_with_version(session)
        repository = WorkflowPackageRepository(session)

        repository.update_package(package, name="Updated Market Review", status="active")
        session.commit()

        assert repository.get_by_key("market_review") is not None
        assert [(item.key, item.status) for item in repository.list_packages()] == [
            ("market_review", "active")
        ]
        assert [(item.key, item.status) for item in repository.list_packages(status="draft")] == []


def test_package_versions_are_immutable(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        _package, version = _create_package_with_version(session)
        repository = WorkflowPackageRepository(session)

        with pytest.raises(ApiError) as excinfo:
            repository.update_version(version, manifest_source="mutated")

        assert excinfo.value.code == "workflow_package_version_immutable"
        assert (
            version.manifest_source
            == "apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n"
        )
