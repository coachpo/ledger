from __future__ import annotations

from sqlalchemy import and_, func, select

from app.models.persona_profile import PersonaProfile
from app.repositories.base import BaseRepository


class PersonaProfileRepository(BaseRepository[PersonaProfile]):
    model = PersonaProfile

    def list_latest_versions(
        self,
        *,
        origin: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        enabled: bool | None = None,
    ) -> list[PersonaProfile]:
        latest_versions = select(
            self.model.key.label("key"),
            func.max(self.model.version).label("version"),
        )
        if origin is not None:
            latest_versions = latest_versions.where(self.model.origin == origin)
        if status is not None:
            latest_versions = latest_versions.where(self.model.status == status)
        if kind is not None:
            latest_versions = latest_versions.where(self.model.kind == kind)
        if enabled is not None:
            latest_versions = latest_versions.where(self.model.enabled.is_(enabled))
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

    def list_versions(self, key: str, *, origin: str | None = None) -> list[PersonaProfile]:
        statement = select(self.model).where(self.model.key == key)
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        statement = statement.order_by(
            self.model.version.desc(), self.model.created_at.desc(), self.model.id.desc()
        )
        return self._list(statement)

    def get_by_key_version(
        self, key: str, version: int, *, origin: str | None = None
    ) -> PersonaProfile | None:
        statement = select(self.model).where(self.model.key == key, self.model.version == version)
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def get_active_by_key(self, key: str, *, origin: str | None = None) -> PersonaProfile | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "ACTIVE")
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def get_draft_by_key(self, key: str, *, origin: str | None = None) -> PersonaProfile | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "DRAFT")
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def get_draft_by_handle(
        self, handle: str, *, origin: str | None = None
    ) -> PersonaProfile | None:
        statement = select(self.model).where(
            self.model.handle == handle, self.model.status == "DRAFT"
        )
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def get_active_by_handle(
        self, handle: str, *, origin: str | None = None
    ) -> PersonaProfile | None:
        statement = select(self.model).where(
            self.model.handle == handle, self.model.status == "ACTIVE"
        )
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def get_active_by_canonical_target_id(
        self, canonical_target_id: str, *, origin: str | None = None
    ) -> PersonaProfile | None:
        statement = select(self.model).where(
            self.model.canonical_target_id == canonical_target_id,
            self.model.status == "ACTIVE",
        )
        if origin is not None:
            statement = statement.where(self.model.origin == origin)
        return self._get_by_statement(statement)

    def resolve_version(
        self, key: str, version: int | None, *, origin: str | None = None
    ) -> PersonaProfile | None:
        if version is None:
            return self.get_active_by_key(key, origin=origin)
        return self.get_by_key_version(key, version, origin=origin)

    def has_origin(self, key: str, origin: str) -> bool:
        statement = (
            select(self.model.id).where(self.model.key == key, self.model.origin == origin).limit(1)
        )
        return self.session.scalar(statement) is not None
