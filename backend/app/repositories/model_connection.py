from __future__ import annotations

from sqlalchemy import select

from app.models.model_connection import ModelConnection
from app.repositories.base import BaseRepository


class ModelConnectionRepository(BaseRepository[ModelConnection]):
    model = ModelConnection

    def list_connections(self, *, status: str | None = None) -> list[ModelConnection]:
        statement = select(self.model)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(
            self.model.status.asc(),
            self.model.name.asc(),
            self.model.id.asc(),
        )
        return self._list(statement)

    def list_active(self) -> list[ModelConnection]:
        return self.list_connections(status="active")


__all__ = ["ModelConnectionRepository"]
