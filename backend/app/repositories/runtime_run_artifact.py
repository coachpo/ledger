from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select

from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.repositories.base import BaseRepository


class RuntimeRunArtifactRepository(BaseRepository[RuntimeRunArtifact]):
    model = RuntimeRunArtifact

    def get_for_run(self, run_id: int) -> RuntimeRunArtifact | None:
        statement = select(self.model).where(self.model.run_id == run_id)
        return self._get_by_statement(statement)

    def list_by_run_ids(self, run_ids: Iterable[int]) -> list[RuntimeRunArtifact]:
        ids = sorted(set(run_ids))
        if not ids:
            return []
        statement = select(self.model).where(self.model.run_id.in_(ids))
        return self._list(statement)

    def list_all(
        self,
        *,
        run_id: int | None = None,
        caller_type: str | None = None,
        caller_id: int | None = None,
        workflow_spec_key: str | None = None,
        persona_profile_key: str | None = None,
        capability_key: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RuntimeRunArtifact]:
        statement = select(self.model)
        if caller_type is not None or caller_id is not None or workflow_spec_key is not None:
            statement = statement.join(RuntimeRun, RuntimeRun.id == self.model.run_id)
        if run_id is not None:
            statement = statement.where(self.model.run_id == run_id)
        if caller_type is not None:
            statement = statement.where(RuntimeRun.caller_type == caller_type)
        if caller_id is not None:
            statement = statement.where(RuntimeRun.caller_id == caller_id)
        if workflow_spec_key is not None:
            statement = statement.where(RuntimeRun.workflow_spec_key == workflow_spec_key)
        if persona_profile_key is not None:
            statement = statement.where(
                self.model.resolved_persona_profile_refs.contains(
                    [{"personaProfileKey": persona_profile_key}]
                )
            )
        if capability_key is not None:
            statement = statement.where(
                self.model.resolved_capabilities.contains([{"capabilityKey": capability_key}])
            )

        statement = statement.order_by(self.model.created_at.desc(), self.model.run_id.desc())
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)
