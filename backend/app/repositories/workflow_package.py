from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.models.workflow_package import WorkflowPackage
from app.repositories.base import BaseRepository


class WorkflowPackageRepository(BaseRepository[WorkflowPackage]):
    model = WorkflowPackage

    def list_packages(self) -> list[WorkflowPackage]:
        statement = select(self.model).order_by(self.model.key.asc(), self.model.id.asc())
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
        manifest_source: str,
        manifest_hash: str,
        package_definition: dict[str, Any],
        compiled_plan: dict[str, Any],
        compiled_hash: str,
        extension_dependencies: list[dict[str, Any]] | None = None,
    ) -> WorkflowPackage:
        package = WorkflowPackage(
            key=key,
            name=name,
            description=description,
            manifest_source=manifest_source,
            manifest_hash=manifest_hash,
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=compiled_hash,
            extension_dependencies=list(extension_dependencies or []),
        )
        return self.add(package)

    def update_package(self, package: WorkflowPackage, **fields: object) -> WorkflowPackage:
        for field_name, value in fields.items():
            setattr(package, field_name, value)
        return self.add(package)
