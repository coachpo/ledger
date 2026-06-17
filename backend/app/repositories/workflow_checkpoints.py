from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import select

from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.models.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
)
from app.repositories.base import BaseRepository


class WorkflowCheckpointRepository(BaseRepository[WorkflowCheckpoint]):
    model: ClassVar[type[WorkflowCheckpoint]] = WorkflowCheckpoint

    def create_checkpoint(
        self,
        *,
        checkpoint_id: str,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
        run_id: int,
        package_key: str,
        workflow_key: str,
        checkpoint_type: str,
        sequence: int,
        state_json: dict[str, Any],
        retention: str,
        agent_key: str | None = None,
        step_id: str | None = None,
        invocation_id: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> WorkflowCheckpoint:
        if checkpoint_type == "run_finalize":
            existing = self.get_run_finalize_checkpoint(
                package_key=package_key,
                workflow_key=workflow_key,
                run_id=run_id,
                owner_type=owner_type,
                owner_id=owner_id,
            )
            if existing is not None:
                return existing
        checkpoint = self.model(
            checkpoint_id=checkpoint_id,
            owner_type=owner_type,
            owner_id=owner_id,
            run_id=run_id,
            package_key=package_key,
            workflow_key=workflow_key,
            agent_key=agent_key,
            step_id=step_id,
            invocation_id=invocation_id,
            checkpoint_type=checkpoint_type,
            sequence=sequence,
            state_json=state_json,
            retention=retention,
            metadata_json=metadata_json or {},
        )
        return self.add(checkpoint)

    def get_run_finalize_checkpoint(
        self,
        *,
        package_key: str,
        workflow_key: str,
        run_id: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowCheckpoint | None:
        statement = select(self.model).where(
            self.model.owner_type == owner_type,
            self.model.owner_id == owner_id,
            self.model.package_key == package_key,
            self.model.workflow_key == workflow_key,
            self.model.run_id == run_id,
            self.model.checkpoint_type == "run_finalize",
            self.model.agent_key.is_(None),
            self.model.step_id.is_(None),
            self.model.invocation_id.is_(None),
        )
        statement = statement.order_by(self.model.sequence.desc(), self.model.id.desc()).limit(1)
        return self.session.scalar(statement)

    def list_checkpoints_for_run(
        self,
        *,
        package_key: str,
        workflow_key: str,
        run_id: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowCheckpoint]:
        statement = (
            select(self.model)
            .where(
                self.model.package_key == package_key,
                self.model.owner_type == owner_type,
                self.model.owner_id == owner_id,
                self.model.workflow_key == workflow_key,
                self.model.run_id == run_id,
            )
            .order_by(self.model.sequence.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def get_latest_checkpoint(
        self,
        *,
        package_key: str,
        workflow_key: str,
        run_id: int,
        checkpoint_type: str,
        agent_key: str | None = None,
        step_id: str | None = None,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowCheckpoint | None:
        statement = select(self.model).where(
            self.model.owner_type == owner_type,
            self.model.owner_id == owner_id,
            self.model.package_key == package_key,
            self.model.workflow_key == workflow_key,
            self.model.run_id == run_id,
            self.model.checkpoint_type == checkpoint_type,
        )
        if agent_key is None:
            statement = statement.where(self.model.agent_key.is_(None))
        else:
            statement = statement.where(self.model.agent_key == agent_key)
        if step_id is None:
            statement = statement.where(self.model.step_id.is_(None))
        else:
            statement = statement.where(self.model.step_id == step_id)
        statement = statement.order_by(self.model.sequence.desc(), self.model.id.desc()).limit(1)
        return self.session.scalar(statement)


__all__ = ["WorkflowCheckpointRepository"]
