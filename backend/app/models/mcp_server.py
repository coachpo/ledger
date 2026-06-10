from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, EncryptedJSONB, IdMixin, TimestampMixin


def _normalize_string_sequence(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)):
        normalized = str(value).strip()
        return [normalized] if normalized else []
    if not isinstance(value, Sequence):
        return []
    return [str(entry).strip() for entry in value if str(entry).strip()]


def _normalize_string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        normalized_key = str(raw_key).strip()
        normalized_value = str(raw_value).strip() if raw_value is not None else ""
        if normalized_key and normalized_value:
            normalized[normalized_key] = normalized_value
    return normalized


class McpServer(IdMixin, TimestampMixin, Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated')",
            name="ck_mcp_servers_status",
        ),
        CheckConstraint("version > 0", name="ck_mcp_servers_version_positive"),
        UniqueConstraint("key", "version", name="uq_mcp_servers_key_version"),
        Index("ix_mcp_servers_key", "key"),
        Index("ix_mcp_servers_status", "status"),
        Index(
            "uq_mcp_servers_published_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'published'"),
        ),
        Index(
            "uq_mcp_servers_draft_key",
            "key",
            unique=True,
            postgresql_where=sql_text("status = 'draft'"),
        ),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
    config: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )

    def _mutable_flat_config(self) -> dict[str, Any]:
        return dict(self.config) if isinstance(self.config, dict) else {}

    def _set_flat_field(self, field_name: str, value: object) -> None:
        next_config = self._mutable_flat_config()
        if value is None:
            next_config.pop(field_name, None)
        else:
            next_config[field_name] = value
        self.config = next_config

    @property
    def flat_config(self) -> dict[str, Any]:
        return self._mutable_flat_config()

    @property
    def name(self) -> str:
        return str(self.flat_config.get("name", ""))

    @name.setter
    def name(self, value: object) -> None:
        self._set_flat_field("name", "" if value is None else str(value))

    @property
    def description(self) -> str:
        return str(self.flat_config.get("description", ""))

    @description.setter
    def description(self, value: object) -> None:
        self._set_flat_field("description", "" if value is None else str(value))

    @property
    def transport(self) -> str:
        return str(self.flat_config.get("transport", ""))

    @transport.setter
    def transport(self, value: object) -> None:
        self._set_flat_field("transport", None if value is None else str(value))

    @property
    def enabled(self) -> bool:
        return bool(self.flat_config.get("enabled", False))

    @enabled.setter
    def enabled(self, value: object) -> None:
        self._set_flat_field("enabled", bool(value))

    @property
    def command(self) -> str | None:
        raw_command = self.flat_config.get("command")
        return str(raw_command) if raw_command is not None else None

    @command.setter
    def command(self, value: object) -> None:
        normalized = str(value).strip() if value is not None else ""
        self._set_flat_field("command", normalized or None)

    @property
    def args(self) -> list[str]:
        return _normalize_string_sequence(self.flat_config.get("args"))

    @args.setter
    def args(self, value: object) -> None:
        self._set_flat_field("args", _normalize_string_sequence(value))

    @property
    def env(self) -> dict[str, str]:
        return _normalize_string_mapping(self.flat_config.get("env"))

    @env.setter
    def env(self, value: object) -> None:
        self._set_flat_field("env", _normalize_string_mapping(value))

    @property
    def url(self) -> str | None:
        raw_url = self.flat_config.get("url")
        return str(raw_url) if raw_url is not None else None

    @url.setter
    def url(self, value: object) -> None:
        normalized = str(value).strip() if value is not None else ""
        self._set_flat_field("url", normalized or None)

    @property
    def headers(self) -> dict[str, str]:
        return _normalize_string_mapping(self.flat_config.get("headers"))

    @headers.setter
    def headers(self, value: object) -> None:
        self._set_flat_field("headers", _normalize_string_mapping(value))


__all__ = ["EncryptedJSONB", "McpServer"]
