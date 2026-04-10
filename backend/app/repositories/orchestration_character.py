from __future__ import annotations

from sqlalchemy import select

from app.models.orchestration_character import OrchestrationCharacter
from app.repositories.base import BaseRepository


class OrchestrationCharacterRepository(BaseRepository[OrchestrationCharacter]):
    model = OrchestrationCharacter

    def list_all(self) -> list[OrchestrationCharacter]:
        statement = select(self.model).order_by(self.model.created_at.desc(), self.model.id.desc())
        return self._list(statement)

    def get_by_handle(self, handle: str) -> OrchestrationCharacter | None:
        statement = select(self.model).where(self.model.handle == handle)
        return self._get_by_statement(statement)

    def list_enabled_for_catalog(self) -> list[OrchestrationCharacter]:
        statement = (
            select(self.model)
            .join(self.model.role)
            .where(self.model.enabled.is_(True))
            .where(self.model.role.has(enabled=True))
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)
