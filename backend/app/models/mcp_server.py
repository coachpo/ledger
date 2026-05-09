from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping, Sequence
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


def flatten_mcp_server_config(config: object, *, key: str) -> dict[str, Any] | None:
    if not isinstance(config, Mapping):
        return {}

    raw_config = dict(config)
    if "mcpServers" not in raw_config:
        return raw_config

    raw_servers = raw_config.get("mcpServers")
    if not isinstance(raw_servers, Mapping):
        return None

    raw_entry = raw_servers.get(key)
    if not isinstance(raw_entry, Mapping):
        return None
    return dict(raw_entry)


def flatten_mcp_server_storage_payload(
    payload: object,
    *,
    key: str,
) -> tuple[dict[str, Any], bool] | None:
    if not isinstance(payload, Mapping):
        return None

    raw_payload = dict(payload)
    decrypted_payload = (
        _decrypt_payload(raw_payload) if _is_encrypted_payload(raw_payload) else raw_payload
    )
    flattened_payload = flatten_mcp_server_config(decrypted_payload, key=key)
    if flattened_payload is None:
        return None
    if flattened_payload == decrypted_payload:
        return raw_payload, False
    if _is_encrypted_payload(raw_payload):
        return _encrypt_payload(flattened_payload), True
    return flattened_payload, True


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


def _legacy_auth_to_headers(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    header_name = str(value.get("header", "")).strip()
    api_key = str(value.get("apiKey", "")).strip()
    if not header_name or not api_key:
        return {}
    return {header_name: api_key}


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

    def _flat_config_key(self) -> str:
        raw_key = getattr(self, "key", "")
        return str(raw_key).strip()

    def _mutable_flat_config(self) -> dict[str, Any]:
        raw_config = self.config if isinstance(self.config, dict) else {}
        flattened_config = flatten_mcp_server_config(raw_config, key=self._flat_config_key())
        if flattened_config is None:
            return {}
        return dict(flattened_config)

    def _set_flat_field(self, field_name: str, value: object) -> None:
        next_config = self._mutable_flat_config()
        if value is None:
            next_config.pop(field_name, None)
        else:
            next_config[field_name] = value
        self.config = next_config

    @property
    def flat_config(self) -> dict[str, Any]:
        flattened_config = flatten_mcp_server_config(self.config, key=self._flat_config_key())
        return flattened_config if flattened_config is not None else {}

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

    @property
    def auth(self) -> dict[str, str]:
        headers = self.headers
        if not headers:
            return {}
        header_name, api_key = next(iter(headers.items()))
        return {"header": header_name, "apiKey": api_key}

    @auth.setter
    def auth(self, value: object) -> None:
        self.headers = _legacy_auth_to_headers(value)


__all__ = [
    "EncryptedJSONB",
    "McpServer",
    "flatten_mcp_server_config",
    "flatten_mcp_server_storage_payload",
]
