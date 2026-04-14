from __future__ import annotations

from sqlalchemy import select

from app.models.runtime_flag_change_event import RuntimeFlagChangeEvent
from app.repositories.base import BaseRepository


class RuntimeFlagChangeEventRepository(BaseRepository[RuntimeFlagChangeEvent]):
    model = RuntimeFlagChangeEvent

    def list_all(
        self,
        *,
        flag_key: str | None = None,
        result: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RuntimeFlagChangeEvent]:
        statement = select(self.model)
        if flag_key is not None:
            statement = statement.where(self.model.flag_key == flag_key)
        if result is not None:
            statement = statement.where(self.model.result == result)
        statement = statement.order_by(self.model.created_at.desc(), self.model.id.desc())
        if offset > 0:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return self._list(statement)

    def list_for_flag(self, flag_key: str) -> list[RuntimeFlagChangeEvent]:
        return self.list_all(flag_key=flag_key)
