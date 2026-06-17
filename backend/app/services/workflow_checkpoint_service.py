from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.workflow_checkpoint import WorkflowCheckpoint
from app.repositories.workflow_checkpoints import WorkflowCheckpointRepository
from app.schemas.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
    WorkflowCheckpointRead,
    WorkflowCheckpointRecord,
    WorkflowCheckpointScope,
)


class WorkflowCheckpointService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowCheckpointRepository = WorkflowCheckpointRepository(session)

    def record_checkpoint(
        self,
        *,
        scope: WorkflowCheckpointScope,
        checkpoint: WorkflowCheckpointRecord,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowCheckpointRead:
        row = self.repository.create_checkpoint(
            checkpoint_id=f"workflow_checkpoint_{uuid4().hex}",
            owner_type=owner_type,
            owner_id=owner_id,
            run_id=scope.run_id,
            package_key=scope.package_key,
            workflow_key=scope.workflow_key,
            agent_key=scope.agent_key,
            step_id=scope.step_id,
            invocation_id=scope.invocation_id,
            checkpoint_type=checkpoint.checkpoint_type,
            sequence=checkpoint.sequence,
            state_json=checkpoint.state,
            retention=checkpoint.retention,
            metadata_json=checkpoint.metadata,
        )
        self.session.flush()
        return self._read(row)

    def list_for_run(
        self,
        *,
        package_key: str,
        workflow_key: str,
        run_id: int,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> list[WorkflowCheckpointRead]:
        return [
            self._read(row)
            for row in self.repository.list_checkpoints_for_run(
                package_key=package_key,
                workflow_key=workflow_key,
                run_id=run_id,
                owner_type=owner_type,
                owner_id=owner_id,
            )
        ]

    def _read(self, row: WorkflowCheckpoint) -> WorkflowCheckpointRead:
        return WorkflowCheckpointRead(
            checkpoint_id=row.checkpoint_id,
            checkpoint_type=row.checkpoint_type,
            sequence=row.sequence,
            state=row.state_json,
            retention=row.retention,
            metadata=row.metadata_json,
            created_at=row.created_at,
            scope=WorkflowCheckpointScope(
                package_key=row.package_key,
                workflow_key=row.workflow_key,
                run_id=row.run_id,
                agent_key=row.agent_key,
                step_id=row.step_id,
                invocation_id=row.invocation_id,
            ),
        )


__all__ = ["WorkflowCheckpointService"]
