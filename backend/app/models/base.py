from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
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
_ENCRYPTED_PAYLOAD_VERSION = 2


def _build_fernet(key_material: str) -> Fernet:
    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fernet = _build_fernet(get_settings().agent_platform_encryption_key)
    ciphertext = fernet.encrypt(json.dumps(payload).encode())
    return {
        _ENCRYPTED_PAYLOAD_MARKER: True,
        "version": _ENCRYPTED_PAYLOAD_VERSION,
        "ciphertext": ciphertext.decode("ascii"),
    }


def _is_encrypted_payload(payload: object) -> bool:
    return isinstance(payload, dict) and bool(payload.get(_ENCRYPTED_PAYLOAD_MARKER))


def _decrypt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}
    if not _is_encrypted_payload(payload):
        raise ValueError("Invalid encrypted JSON payload.")
    if payload.get("version") != _ENCRYPTED_PAYLOAD_VERSION:
        raise ValueError("Unsupported encrypted JSON payload version.")

    fernet = _build_fernet(get_settings().agent_platform_encryption_key)
    try:
        plaintext = fernet.decrypt(str(payload["ciphertext"]).encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("Invalid encrypted JSON payload.") from exc
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
