from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.core.errors import business_rule_error
from app.models.platform_reference import WorkflowPackageVersionModelConnection
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
from app.repositories.base import BaseRepository


class WorkflowPackageRepository(BaseRepository[WorkflowPackage]):
    model = WorkflowPackage

    def list_packages(
        self,
        *,
        status: str | None = None,
    ) -> list[WorkflowPackage]:
        statement = select(self.model)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(self.model.key.asc(), self.model.id.asc())
        return self._list(statement)

    def get_by_key(self, key: str) -> WorkflowPackage | None:
        statement = select(self.model).where(self.model.key == key)
        statement = statement.order_by(self.model.id.asc())
        return self._get_by_statement(statement)

    def create_package(
        self,
        *,
        key: str,
        name: str,
        description: str = "",
        status: str = "draft",
        draft_source: str = "",
    ) -> WorkflowPackage:
        package = WorkflowPackage(
            key=key,
            name=name,
            description=description,
            status=status,
            draft_source=draft_source,
        )
        return self.add(package)

    def update_package(self, package: WorkflowPackage, **fields: object) -> WorkflowPackage:
        for field_name, value in fields.items():
            setattr(package, field_name, value)
        return self.add(package)

    def create_version(
        self,
        package: WorkflowPackage,
        *,
        manifest_source: str,
        manifest_hash: str,
        package_definition: dict[str, Any],
        compiled_plan: dict[str, Any],
        compiled_hash: str,
        validation_summary: dict[str, Any] | None = None,
        launched_at: datetime | None = None,
        model_connection_refs: list[tuple[int, str]] | None = None,
    ) -> WorkflowPackageVersion:
        self.session.flush()
        package_id = package.id
        locked_package = self.session.scalar(
            select(WorkflowPackage).where(WorkflowPackage.id == package_id).with_for_update()
        )
        if locked_package is None:
            raise business_rule_error(
                "workflow_package_not_persisted",
                "Workflow package must be persisted before a version can be created",
            )
        next_version = (
            self.session.scalar(
                select(func.coalesce(func.max(WorkflowPackageVersion.version), 0)).where(
                    WorkflowPackageVersion.package_id == locked_package.id
                )
            )
            or 0
        ) + 1
        version = WorkflowPackageVersion(
            package_id=locked_package.id,
            version=next_version,
            manifest_source=manifest_source,
            manifest_hash=manifest_hash,
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=compiled_hash,
            validation_summary=dict(validation_summary or {}),
            launched_at=launched_at,
        )
        self.session.add(version)
        self.session.flush()
        for model_connection_id, model_connection_key in dict(model_connection_refs or []).items():
            self.session.add(
                WorkflowPackageVersionModelConnection(
                    workflow_package_version_id=version.id,
                    model_connection_id=model_connection_id,
                    model_connection_key=model_connection_key,
                )
            )
        locked_package.latest_version_id = version.id
        return version

    def list_versions(self, package_id: int) -> list[WorkflowPackageVersion]:
        statement = (
            select(WorkflowPackageVersion)
            .where(WorkflowPackageVersion.package_id == package_id)
            .order_by(WorkflowPackageVersion.version.desc(), WorkflowPackageVersion.id.desc())
        )
        return list(self.session.scalars(statement))

    def get_version(self, package_id: int, version: int) -> WorkflowPackageVersion | None:
        statement = select(WorkflowPackageVersion).where(
            WorkflowPackageVersion.package_id == package_id,
            WorkflowPackageVersion.version == version,
        )
        return self.session.scalar(statement)

    def get_latest_version(self, package_id: int) -> WorkflowPackageVersion | None:
        statement = (
            select(WorkflowPackageVersion)
            .where(WorkflowPackageVersion.package_id == package_id)
            .order_by(WorkflowPackageVersion.version.desc(), WorkflowPackageVersion.id.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def update_version(
        self,
        version: WorkflowPackageVersion,
        **fields: object,
    ) -> WorkflowPackageVersion:
        del version, fields
        raise business_rule_error(
            "workflow_package_version_immutable",
            "Workflow package versions are immutable once created",
        )
