from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.models.base import Base, IdMixin, TimestampMixin

_ENCRYPTED_PAYLOAD_MARKER = "__encrypted__"
_ENCRYPTED_PAYLOAD_VERSION = 1


def _encryption_key_bytes() -> bytes:
    configured_key = get_settings().agent_platform_encryption_key
    return hashlib.sha256(configured_key.encode("utf-8")).digest()


def _xor_stream(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("Encrypted MCP payload sizes must match.")
    return bytes(left[index] ^ right[index] for index in range(len(left)))


def _derive_keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    blocks: list[bytes] = []
    counter = 0
    while sum(len(block) for block in blocks) < length:
        blocks.append(hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest())
        counter += 1
    return b"".join(blocks)[:length]


def _encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _encrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    key = _encryption_key_bytes()
    nonce = secrets.token_bytes(16)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = _xor_stream(plaintext, _derive_keystream(key, nonce, len(plaintext)))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        _ENCRYPTED_PAYLOAD_MARKER: True,
        "version": _ENCRYPTED_PAYLOAD_VERSION,
        "nonce": _encode_bytes(nonce),
        "ciphertext": _encode_bytes(ciphertext),
        "mac": _encode_bytes(mac),
    }


def _is_encrypted_payload(payload: object) -> bool:
    return isinstance(payload, dict) and bool(payload.get(_ENCRYPTED_PAYLOAD_MARKER))


def _decrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not _is_encrypted_payload(payload):
        return payload
    if payload.get("version") != _ENCRYPTED_PAYLOAD_VERSION:
        raise ValueError("Unsupported encrypted MCP payload version.")

    key = _encryption_key_bytes()
    nonce = _decode_bytes(str(payload["nonce"]))
    ciphertext = _decode_bytes(str(payload["ciphertext"]))
    mac = _decode_bytes(str(payload["mac"]))
    expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Invalid encrypted MCP payload.")

    plaintext = _xor_stream(ciphertext, _derive_keystream(key, nonce, len(ciphertext)))
    decoded_payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(decoded_payload, dict):
        raise ValueError("Encrypted MCP payload must decode to an object.")
    return decoded_payload


class EncryptedJSONB(TypeDecorator[dict[str, Any]]):
    impl = JSONB
    cache_ok = True

    def process_bind_param(
        self,
        value: dict[str, Any] | None,
        dialect: Dialect,
    ) -> dict[str, Any]:
        del dialect
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("MCP payloads must be stored as JSON objects.")
        if _is_encrypted_payload(value):
            return value
        return _encrypt_payload(value)

    def process_result_value(
        self,
        value: dict[str, Any] | None,
        dialect: Dialect,
    ) -> dict[str, Any]:
        del dialect
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("Stored MCP payload rows must decode to JSON objects.")
        return _decrypt_payload(value)


class McpServer(IdMixin, TimestampMixin, Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated', 'archived')",
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

    @property
    def config_entry(self) -> dict[str, Any]:
        raw_servers = self.config.get("mcpServers") if isinstance(self.config, dict) else None
        if not isinstance(raw_servers, dict):
            return {}
        raw_entry = raw_servers.get(self.key)
        return raw_entry if isinstance(raw_entry, dict) else {}

    @property
    def name(self) -> str:
        return str(self.config_entry.get("name", ""))

    @property
    def description(self) -> str:
        return str(self.config_entry.get("description", ""))

    @property
    def transport(self) -> str:
        return str(self.config_entry.get("transport", ""))

    @property
    def enabled(self) -> bool:
        return bool(self.config_entry.get("enabled", False))

    @property
    def command(self) -> str | None:
        raw_command = self.config_entry.get("command")
        return str(raw_command) if raw_command is not None else None

    @property
    def args(self) -> list[str]:
        raw_args = self.config_entry.get("args")
        if not isinstance(raw_args, list):
            return []
        return [str(entry) for entry in raw_args if str(entry).strip()]

    @property
    def env(self) -> dict[str, str]:
        raw_env = self.config_entry.get("env")
        if not isinstance(raw_env, dict):
            return {}
        return {str(key): str(value) for key, value in raw_env.items()}

    @property
    def url(self) -> str | None:
        raw_url = self.config_entry.get("url")
        return str(raw_url) if raw_url is not None else None

    @property
    def headers(self) -> dict[str, str]:
        raw_headers = self.config_entry.get("headers")
        if not isinstance(raw_headers, dict):
            return {}
        return {str(key): str(value) for key, value in raw_headers.items()}


__all__ = ["EncryptedJSONB", "McpServer"]
