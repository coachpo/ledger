from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker


class RuntimeToolError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code: str = code
        self.message: str = message
        self.details: list[dict[str, object]] = list(details or [])


@dataclass(frozen=True)
class RuntimeToolContext:
    session_factory: sessionmaker[Session]
    capability_references: Sequence[dict[str, object]]


class RuntimeToolParser(Protocol):
    def __call__(self, arguments_json: str) -> dict[str, object]: ...


class RuntimeToolExecutor(Protocol):
    def __call__(
        self,
        context: RuntimeToolContext,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class RuntimeToolSpec:
    key: str
    openai_function_name: str
    display_name: str
    description: str
    parameters_schema: dict[str, object]
    guidance: str
    sort_order: int
    denied_code: str
    denied_message: str
    parser: RuntimeToolParser
    executor: RuntimeToolExecutor


__all__ = [
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolExecutor",
    "RuntimeToolParser",
    "RuntimeToolSpec",
]
