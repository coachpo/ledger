from __future__ import annotations

from typing import ClassVar

from sqlalchemy import select

from app.models.workflow_package import WorkflowPackageSecretBinding
from app.repositories.base import BaseRepository


class WorkflowPackageSecretBindingRepository(BaseRepository[WorkflowPackageSecretBinding]):
    model: ClassVar[type[WorkflowPackageSecretBinding]] = WorkflowPackageSecretBinding

    def list_for_package(self, package_id: int) -> list[WorkflowPackageSecretBinding]:
        statement = (
            select(self.model)
            .where(self.model.package_id == package_id)
            .order_by(self.model.key.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_keys_for_package(self, package_id: int) -> set[str]:
        statement = select(self.model.key).where(self.model.package_id == package_id)
        return {str(key) for key in self.session.scalars(statement)}

    def get_by_key(
        self,
        package_id: int,
        key: str,
    ) -> WorkflowPackageSecretBinding | None:
        statement = select(self.model).where(
            self.model.package_id == package_id,
            self.model.key == key,
        )
        return self.session.scalar(statement)

    def upsert(
        self,
        *,
        package_id: int,
        key: str,
        value: str,
    ) -> WorkflowPackageSecretBinding:
        binding = self.get_by_key(package_id, key)
        payload = {"value": value}
        if binding is None:
            binding = WorkflowPackageSecretBinding(
                package_id=package_id,
                key=key,
                secret_payload=payload,
            )
        else:
            binding.secret_payload = payload
        return self.add(binding)


__all__ = ["WorkflowPackageSecretBindingRepository"]
