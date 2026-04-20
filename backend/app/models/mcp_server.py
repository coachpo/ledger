from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.models.base import Base, IdMixin, TimestampMixin

_AUTH_ENVELOPE_MARKER = "__encrypted__"
_AUTH_ENVELOPE_VERSION = 1


def _encryption_key_bytes() -> bytes:
    configured_key = get_settings().agent_platform_encryption_key
    return hashlib.sha256(configured_key.encode("utf-8")).digest()


def _xor_stream(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("Encrypted MCP auth payload sizes must match.")
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


def _encrypt_auth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    key = _encryption_key_bytes()
    nonce = secrets.token_bytes(16)
    plaintext = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ciphertext = _xor_stream(plaintext, _derive_keystream(key, nonce, len(plaintext)))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    return {
        _AUTH_ENVELOPE_MARKER: True,
        "version": _AUTH_ENVELOPE_VERSION,
        "nonce": _encode_bytes(nonce),
        "ciphertext": _encode_bytes(ciphertext),
        "mac": _encode_bytes(mac),
    }


def _is_encrypted_auth_envelope(payload: object) -> bool:
    return isinstance(payload, dict) and bool(payload.get(_AUTH_ENVELOPE_MARKER))


def _decrypt_auth_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not _is_encrypted_auth_envelope(payload):
        return payload
    if payload.get("version") != _AUTH_ENVELOPE_VERSION:
        raise ValueError("Unsupported MCP auth envelope version.")

    key = _encryption_key_bytes()
    nonce = _decode_bytes(str(payload["nonce"]))
    ciphertext = _decode_bytes(str(payload["ciphertext"]))
    mac = _decode_bytes(str(payload["mac"]))
    expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Invalid encrypted MCP auth payload.")

    plaintext = _xor_stream(ciphertext, _derive_keystream(key, nonce, len(ciphertext)))
    decoded_payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(decoded_payload, dict):
        raise ValueError("Encrypted MCP auth payload must decode to an object.")
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
            raise TypeError("MCP auth must be stored as a JSON object.")
        if _is_encrypted_auth_envelope(value):
            return value
        return _encrypt_auth_payload(value)

    def process_result_value(
        self,
        value: dict[str, Any] | None,
        dialect: Dialect,
    ) -> dict[str, Any]:
        del dialect
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise TypeError("MCP auth rows must decode to JSON objects.")
        return _decrypt_auth_payload(value)


class McpServer(IdMixin, TimestampMixin, Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'deprecated', 'archived')",
            name="ck_mcp_servers_status",
        ),
        CheckConstraint(
            "transport IN ('stdio', 'http-sse')",
            name="ck_mcp_servers_transport",
        ),
        CheckConstraint(
            "((transport = 'stdio' AND command IS NOT NULL AND url IS NULL) OR "
            "(transport = 'http-sse' AND url IS NOT NULL AND command IS NULL))",
            name="ck_mcp_servers_target",
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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    transport: Mapped[str] = mapped_column(String(20), nullable=False)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sql_text("true"),
    )
