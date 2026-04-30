from __future__ import annotations

from sqlalchemy import and_, func, select

from app.models.capability import Capability
from app.repositories.base import BaseRepository


class CapabilityRepository(BaseRepository[Capability]):
    model = Capability

    def list_latest_versions(self, *, status: str | None = None) -> list[Capability]:
        latest_versions = select(
            self.model.key.label("key"),
            func.max(self.model.version).label("version"),
        )
        if status is not None:
            latest_versions = latest_versions.where(self.model.status == status)
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

    def list_versions(self, key: str) -> list[Capability]:
        statement = (
            select(self.model)
            .where(self.model.key == key)
            .order_by(self.model.version.desc(), self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)

    def get_by_key_version(self, key: str, version: int) -> Capability | None:
        statement = select(self.model).where(self.model.key == key, self.model.version == version)
        return self._get_by_statement(statement)

    def get_published_by_key(self, key: str) -> Capability | None:
        statement = select(self.model).where(
            self.model.key == key,
            self.model.status == "published",
        )
        return self._get_by_statement(statement)

    def get_draft_by_key(self, key: str) -> Capability | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "draft")
        return self._get_by_statement(statement)

    def resolve_version(self, key: str, version: int | None) -> Capability | None:
        if version is None:
            return self.get_published_by_key(key)
        return self.get_by_key_version(key, version)
