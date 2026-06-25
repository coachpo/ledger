from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator

from app.core.config import get_settings
from app.core.formatting import utcnow


class Base(DeclarativeBase):
    type_annotation_map = {
        Decimal: Numeric(20, 8),
        datetime: DateTime(timezone=True),
        str: String(),
    }


class IdMixin:
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


_ENCRYPTED_PAYLOAD_MARKER = "__encrypted__"
_ENCRYPTED_PAYLOAD_VERSION = 1


def _encryption_key_bytes() -> bytes:
    configured_key = get_settings().agent_platform_encryption_key
    return hashlib.sha256(configured_key.encode("utf-8")).digest()


def _xor_stream(left: bytes, right: bytes) -> bytes:
    if len(left) != len(right):
        raise ValueError("Encrypted JSON payload sizes must match.")
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
        raise ValueError("Unsupported encrypted JSON payload version.")

    key = _encryption_key_bytes()
    nonce = _decode_bytes(str(payload["nonce"]))
    ciphertext = _decode_bytes(str(payload["ciphertext"]))
    mac = _decode_bytes(str(payload["mac"]))
    expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Invalid encrypted JSON payload.")

    plaintext = _xor_stream(ciphertext, _derive_keystream(key, nonce, len(ciphertext)))
    decoded_payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(decoded_payload, dict):
        raise ValueError("Encrypted JSON payload must decode to an object.")
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
            raise TypeError("Encrypted JSON payloads must be stored as JSON objects.")
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
            raise TypeError("Stored encrypted JSON payload rows must decode to JSON objects.")
        return _decrypt_payload(value)
