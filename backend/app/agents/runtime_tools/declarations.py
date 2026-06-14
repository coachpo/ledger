from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

SignalDeckToolDeclarationKind = Literal["native_runtime", "mcp"]


def runtime_model_name_for_tool_key(tool_key: str) -> str:
    return tool_key.replace(".", "_")


@dataclass(frozen=True, slots=True)
class SignalDeckToolDeclaration:
    kind: SignalDeckToolDeclarationKind
    tool_key: str
    model_name: str
    description: str
    input_schema: Mapping[str, object]
    schema_hash: str
    strict: bool = True
    owner_extension_key: str | None = None


__all__ = [
    "SignalDeckToolDeclaration",
    "SignalDeckToolDeclarationKind",
    "runtime_model_name_for_tool_key",
]
