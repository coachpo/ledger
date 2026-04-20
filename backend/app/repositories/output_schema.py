from __future__ import annotations

from sqlalchemy import and_, func, select

from app.models.output_schema import OutputSchema
from app.repositories.base import BaseRepository


class OutputSchemaRepository(BaseRepository[OutputSchema]):
    model = OutputSchema

    def list_latest_versions(
        self,
        *,
        status: str | None = None,
        kind: str | None = None,
    ) -> list[OutputSchema]:
        latest_versions = select(
            self.model.key.label("key"),
            func.max(self.model.version).label("version"),
        )
        if status is not None:
            latest_versions = latest_versions.where(self.model.status == status)
        if kind is not None:
            latest_versions = latest_versions.where(self.model.kind == kind)
        latest_versions = latest_versions.group_by(self.model.key)

        latest_versions_subquery = latest_versions.subquery()
        statement = (
            select(self.model)
            .join(
                latest_versions_subquery,
                and_(
                    self.model.key == latest_versions_subquery.c.key,
                    self.model.version == latest_versions_subquery.c.version,
                ),
            )
            .order_by(self.model.key.asc(), self.model.version.desc())
        )
        return self._list(statement)

    def list_versions(self, key: str, *, kind: str | None = None) -> list[OutputSchema]:
        statement = select(self.model).where(self.model.key == key)
        if kind is not None:
            statement = statement.where(self.model.kind == kind)
        statement = statement.order_by(
            self.model.version.desc(),
            self.model.created_at.desc(),
            self.model.id.desc(),
        )
        return self._list(statement)

    def get_by_key_version(
        self,
        key: str,
        version: int,
        *,
        kind: str | None = None,
    ) -> OutputSchema | None:
        statement = select(self.model).where(self.model.key == key, self.model.version == version)
        if kind is not None:
            statement = statement.where(self.model.kind == kind)
        return self._get_by_statement(statement)

    def get_published_by_key(self, key: str, *, kind: str | None = None) -> OutputSchema | None:
        statement = select(self.model).where(
            self.model.key == key,
            self.model.status == "published",
        )
        if kind is not None:
            statement = statement.where(self.model.kind == kind)
        return self._get_by_statement(statement)

    def get_draft_by_key(self, key: str, *, kind: str | None = None) -> OutputSchema | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "draft")
        if kind is not None:
            statement = statement.where(self.model.kind == kind)
        return self._get_by_statement(statement)

    def list_registry_entries(self, *, status: str = "published") -> list[OutputSchema]:
        return self.list_latest_versions(status=status, kind="shared")

    def resolve_registry_ref(self, key: str, version: int | None = None) -> OutputSchema | None:
        if version is None:
            return self.get_published_by_key(key, kind="shared")
        return self.get_by_key_version(key, version, kind="shared")

    def resolve_version(self, key: str, version: int | None) -> OutputSchema | None:
        if version is None:
            return self.get_published_by_key(key)
        return self.get_by_key_version(key, version)
