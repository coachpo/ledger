from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import select

from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.repositories.base import BaseRepository


class WorkflowCheckpointRepository(BaseRepository[WorkflowCheckpoint]):
    model: ClassVar[type[WorkflowCheckpoint]] = WorkflowCheckpoint

    def create_checkpoint(
        self,
        *,
        checkpoint_id: str,
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
        checkpoint = self.model(
            checkpoint_id=checkpoint_id,
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

    def list_checkpoints_for_run(
        self,
        *,
        package_key: str,
        workflow_key: str,
        run_id: int,
    ) -> list[WorkflowCheckpoint]:
        statement = (
            select(self.model)
            .where(
                self.model.package_key == package_key,
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
    ) -> WorkflowCheckpoint | None:
        statement = select(self.model).where(
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
