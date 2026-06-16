from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.formatting import utcnow
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import (
    WorkflowMemoryContextItem,
    WorkflowMemoryContextPack,
    WorkflowMemoryContextRequest,
    WorkflowMemoryScope,
)


class WorkflowMemoryContextService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

    def build_context_pack(
        self,
        *,
        request: WorkflowMemoryContextRequest,
        now: datetime | None = None,
    ) -> WorkflowMemoryContextPack:
        policy = request.policy
        retrieval = policy.retrieval
        if not policy.enabled or retrieval is None or not retrieval.enabled:
            return WorkflowMemoryContextPack(items=[], policy_scope=request.scope)
        namespaces = tuple(
            namespace for namespace in retrieval.namespaces if namespace == request.scope.namespace
        )
        records = self.repository.list_active_memory(
            package_key=request.scope.package_key,
            workflow_key=request.scope.workflow_key,
            agent_key=request.scope.agent_key,
            step_id=request.scope.step_id,
            namespaces=namespaces,
            now=now or utcnow(),
            limit=retrieval.max_items,
        )
        items = [
            WorkflowMemoryContextItem(
                item_id=record.memory_id,
                content=record.content_json,
                kind=record.kind,
                namespace=record.namespace,
                provenance=record.provenance_json,
                created_at=record.created_at,
                valid_from=record.valid_from,
                expires_at=record.expires_at,
                scope=WorkflowMemoryScope(
                    package_key=record.package_key,
                    workflow_key=record.workflow_key,
                    agent_key=record.agent_key,
                    step_id=record.step_id,
                    namespace=record.namespace,
                ),
                authoritative=False,
            )
            for record in records
            if not retrieval.include_kinds or record.kind in retrieval.include_kinds
        ]
        return WorkflowMemoryContextPack(
            items=items,
            policy_scope=request.scope,
            authoritative=False,
        )


__all__ = ["WorkflowMemoryContextService"]
