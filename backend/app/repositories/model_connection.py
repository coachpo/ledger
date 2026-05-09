from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, TypeGuard, cast

from sqlalchemy import select

from app.models.agent import Agent
from app.models.model_connection import ModelConnection
from app.models.platform_reference import WorkflowPackageVersionModelConnection
from app.models.workflow_package import WorkflowPackage, WorkflowPackageVersion
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

    def list_workflow_package_version_refs(
        self,
        connection_id: int,
    ) -> list[ModelConnectionReference]:
        statement = (
            select(WorkflowPackageVersionModelConnection, WorkflowPackageVersion, WorkflowPackage)
            .join(
                WorkflowPackageVersion,
                WorkflowPackageVersion.id
                == WorkflowPackageVersionModelConnection.workflow_package_version_id,
            )
            .join(WorkflowPackage, WorkflowPackage.id == WorkflowPackageVersion.package_id)
            .where(WorkflowPackageVersionModelConnection.model_connection_id == connection_id)
            .order_by(
                WorkflowPackage.key.asc(),
                WorkflowPackageVersion.version.asc(),
                WorkflowPackageVersion.id.asc(),
            )
        )
        rows = cast(
            list[
                tuple[
                    WorkflowPackageVersionModelConnection, WorkflowPackageVersion, WorkflowPackage
                ]
            ],
            self.session.execute(statement).all(),
        )
        return [
            ModelConnectionReference(
                ref_type="workflowPackageVersion",
                ref_id=version.id,
                ref_key=f"{package.key}@{version.version}",
            )
            for _, version, package in rows
        ]

    def list_agent_refs(self, connection_id: int) -> list[ModelConnectionReference]:
        statement = (
            select(Agent)
            .where(Agent.model_connection_id == connection_id)
            .order_by(Agent.key.asc(), Agent.version.asc(), Agent.id.asc())
        )
        return [
            ModelConnectionReference(
                ref_type="agent",
                ref_id=agent.id,
                ref_key=f"{agent.key}@{agent.version}",
            )
            for agent in self.session.scalars(statement)
        ]

    def list_compiled_plan_refs(self, connection_key: str) -> list[ModelConnectionReference]:
        statement = (
            select(WorkflowPackageVersion, WorkflowPackage)
            .join(WorkflowPackage, WorkflowPackage.id == WorkflowPackageVersion.package_id)
            .order_by(
                WorkflowPackage.key.asc(),
                WorkflowPackageVersion.version.asc(),
                WorkflowPackageVersion.id.asc(),
            )
        )
        rows = cast(
            list[tuple[WorkflowPackageVersion, WorkflowPackage]],
            self.session.execute(statement).all(),
        )
        return [
            ModelConnectionReference(
                ref_type="workflowPackageVersion",
                ref_id=version.id,
                ref_key=f"{package.key}@{version.version}",
            )
            for version, package in rows
            if self._compiled_plan_references_key(version.compiled_plan, connection_key)
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
