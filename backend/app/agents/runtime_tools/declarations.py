from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

SignalDeckToolDeclarationKind = Literal["native_runtime", "mcp"]


@dataclass(frozen=True, slots=True)
class SignalDeckToolDeclaration:
    kind: SignalDeckToolDeclarationKind
    tool_key: str
    model_name: str
    description: str
    input_schema: Mapping[str, Any]
    schema_hash: str
    strict: bool = True
    owner_extension_key: str | None = None


__all__ = [
    "SignalDeckToolDeclaration",
    "SignalDeckToolDeclarationKind",
]
