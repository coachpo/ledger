from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.symbol_name_cache import SymbolNameCache
from app.repositories.base import BaseRepository


class SymbolNameCacheRepository(BaseRepository[SymbolNameCache]):
    model = SymbolNameCache

    def get_by_symbol(self, symbol: str) -> SymbolNameCache | None:
        statement = select(self.model).where(self.model.symbol == symbol)
        return self._get_by_statement(statement)

    def insert_if_missing(self, symbol: str, name: str, fetched_at: datetime) -> bool:
        statement = (
            insert(self.model)
            .values(symbol=symbol, name=name, fetched_at=fetched_at)
            .on_conflict_do_nothing(index_elements=["symbol"])
            .returning(self.model.id)
        )
        inserted_id = self.session.execute(statement).scalar_one_or_none()
        return inserted_id is not None
