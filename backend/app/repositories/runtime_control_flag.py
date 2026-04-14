from __future__ import annotations

from sqlalchemy import select

from app.models.runtime_control_flag import RuntimeControlFlag
from app.repositories.base import BaseRepository


class RuntimeControlFlagRepository(BaseRepository[RuntimeControlFlag]):
    model = RuntimeControlFlag

    def list_all(self) -> list[RuntimeControlFlag]:
        statement = select(self.model).order_by(self.model.flag_key.asc())
        return self._list(statement)

    def get_by_key(self, flag_key: str) -> RuntimeControlFlag | None:
        statement = select(self.model).where(self.model.flag_key == flag_key)
        return self._get_by_statement(statement)
