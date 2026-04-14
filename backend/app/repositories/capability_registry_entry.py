from __future__ import annotations

from sqlalchemy import and_, func, select

from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.repositories.base import BaseRepository


class CapabilityRegistryEntryRepository(BaseRepository[CapabilityRegistryEntry]):
    model = CapabilityRegistryEntry

    def list_latest_versions(
        self,
        *,
        origin: str | None = None,
        status: str | None = None,
        capability_type: str | None = None,
    ) -> list[CapabilityRegistryEntry]:
        latest_versions = select(
            self.model.key.label("key"),
            func.max(self.model.version).label("version"),
        )
        if origin is not None:
            latest_versions = latest_versions.where(self.model.origin == origin)
        if status is not None:
            latest_versions = latest_versions.where(self.model.status == status)
        if capability_type is not None:
            latest_versions = latest_versions.where(self.model.type == capability_type)
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

    def list_versions(self, key: str) -> list[CapabilityRegistryEntry]:
        statement = (
            select(self.model)
            .where(self.model.key == key)
            .order_by(self.model.version.desc(), self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)

    def get_by_key_version(self, key: str, version: int) -> CapabilityRegistryEntry | None:
        statement = select(self.model).where(self.model.key == key, self.model.version == version)
        return self._get_by_statement(statement)

    def get_active_by_key(self, key: str) -> CapabilityRegistryEntry | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "ACTIVE")
        return self._get_by_statement(statement)

    def get_draft_by_key(self, key: str) -> CapabilityRegistryEntry | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "DRAFT")
        return self._get_by_statement(statement)

    def has_origin(self, key: str, origin: str) -> bool:
        statement = (
            select(self.model.id).where(self.model.key == key, self.model.origin == origin).limit(1)
        )
        return self.session.scalar(statement) is not None

    def resolve_version(self, key: str, version: int | None) -> CapabilityRegistryEntry | None:
        if version is None:
            return self.get_active_by_key(key)
        return self.get_by_key_version(key, version)
