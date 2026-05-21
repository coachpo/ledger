from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, TypeGuard, cast

from sqlalchemy import select

from app.models.model_connection import ModelConnection
from app.models.workflow_package import WorkflowPackage
from app.repositories.base import BaseRepository


def _is_string_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


@dataclass(frozen=True)
class ModelConnectionReference:
    ref_type: str
    ref_id: int
    ref_key: str


class ModelConnectionRepository(BaseRepository[ModelConnection]):
    model: ClassVar[type[ModelConnection]] = ModelConnection

    def list_connections(self) -> list[ModelConnection]:
        statement = select(self.model).order_by(
            self.model.name.asc(),
            self.model.id.asc(),
        )
        return self._list(statement)

    def get_by_key(self, key: str) -> ModelConnection | None:
        statement = select(self.model).where(self.model.key == key)
        return self._get_by_statement(statement)

    def list_current_package_refs(self, connection_key: str) -> list[ModelConnectionReference]:
        statement = select(WorkflowPackage).order_by(
            WorkflowPackage.key.asc(),
            WorkflowPackage.id.asc(),
        )
        return [
            ModelConnectionReference(
                ref_type="workflowPackage",
                ref_id=package.id,
                ref_key=package.key,
            )
            for package in self.session.scalars(statement)
            if self._compiled_plan_references_key(package.compiled_plan, connection_key)
        ]

    @staticmethod
    def _compiled_plan_references_key(compiled_plan: object, connection_key: str) -> bool:
        if not _is_string_mapping(compiled_plan):
            return False
        agents = compiled_plan.get("agents")
        if not isinstance(agents, list):
            return False
        for agent in cast(list[object], agents):
            if not _is_string_mapping(agent):
                continue
            if agent.get("modelConnection") == connection_key:
                return True
        return False


__all__ = ["ModelConnectionReference", "ModelConnectionRepository"]
