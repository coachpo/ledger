from __future__ import annotations

from sqlalchemy import select

from app.models.orchestration_role import OrchestrationRole
from app.repositories.base import BaseRepository


class OrchestrationRoleRepository(BaseRepository[OrchestrationRole]):
    model = OrchestrationRole

    def list_all(self) -> list[OrchestrationRole]:
        statement = select(self.model).order_by(self.model.created_at.desc(), self.model.id.desc())
        return self._list(statement)

    def get_by_key(self, key: str) -> OrchestrationRole | None:
        statement = select(self.model).where(self.model.key == key)
        return self._get_by_statement(statement)

    def get_by_name(self, name: str) -> OrchestrationRole | None:
        statement = select(self.model).where(self.model.name == name)
        return self._get_by_statement(statement)
