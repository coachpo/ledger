from __future__ import annotations

from sqlalchemy import and_, func, select

from app.models.mcp_server import McpServer
from app.repositories.base import BaseRepository


class McpServerRepository(BaseRepository[McpServer]):
    model = McpServer

    @staticmethod
    def _matches_runtime_filters(
        server: McpServer,
        *,
        enabled: bool | None = None,
        transport: str | None = None,
    ) -> bool:
        if enabled is not None and server.enabled is not enabled:
            return False
        if transport is not None and server.transport != transport:
            return False
        return True

    def list_latest_versions(
        self,
        *,
        status: str | None = None,
        enabled: bool | None = None,
        transport: str | None = None,
    ) -> list[McpServer]:
        if enabled is None and transport is None:
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

        statement = select(self.model)
        if status is not None:
            statement = statement.where(self.model.status == status)
        statement = statement.order_by(self.model.key.asc(), self.model.version.desc())

        latest_matches: list[McpServer] = []
        seen_keys: set[str] = set()
        for item in self._list(statement):
            if item.key in seen_keys:
                continue
            if not self._matches_runtime_filters(item, enabled=enabled, transport=transport):
                continue
            latest_matches.append(item)
            seen_keys.add(item.key)
        return latest_matches

    def list_versions(self, key: str) -> list[McpServer]:
        statement = (
            select(self.model)
            .where(self.model.key == key)
            .order_by(self.model.version.desc(), self.model.created_at.desc(), self.model.id.desc())
        )
        return self._list(statement)

    def get_by_key_version(self, key: str, version: int) -> McpServer | None:
        statement = select(self.model).where(self.model.key == key, self.model.version == version)
        return self._get_by_statement(statement)

    def get_published_by_key(
        self,
        key: str,
        *,
        enabled: bool | None = None,
    ) -> McpServer | None:
        statement = select(self.model).where(
            self.model.key == key,
            self.model.status == "published",
        )
        result = self._get_by_statement(statement)
        if result is None:
            return None
        if not self._matches_runtime_filters(result, enabled=enabled):
            return None
        return result

    def get_draft_by_key(self, key: str) -> McpServer | None:
        statement = select(self.model).where(self.model.key == key, self.model.status == "draft")
        return self._get_by_statement(statement)

    def resolve_version(
        self,
        key: str,
        version: int | None,
        *,
        enabled: bool | None = None,
    ) -> McpServer | None:
        if version is None:
            return self.get_published_by_key(key, enabled=enabled)
        result = self.get_by_key_version(key, version)
        if result is None:
            return None
        if not self._matches_runtime_filters(result, enabled=enabled):
            return None
        return result
