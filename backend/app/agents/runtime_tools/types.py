from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import Field, field_validator
from sqlalchemy.orm import Session, sessionmaker

from app.schemas.common import CamelModel

if TYPE_CHECKING:
    from app.services.execution_ownership import PackageExecutionOwnership
    from app.services.quote_provider import QuoteProvider
    from app.services.social_sentiment_provider import SocialSentimentSourceAdapter


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
    quote_provider: QuoteProvider | None = None
    social_sentiment_adapters: Sequence[SocialSentimentSourceAdapter] | None = None
    run_id: int | None = None
    agent_key: str | None = None
    agent_version: int | None = None
    agent_name: str | None = None
    package_ownership: PackageExecutionOwnership | None = None
    workflow_key: str | None = None
    workflow_version: int | None = None
    step_id: str | None = None
    slot: str | None = None
    trace_id: str | None = None


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
    owner_extension_key: str | None = None


_WARNING_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


class RuntimeToolWarning(CamelModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    details: dict[str, str] = Field(default_factory=dict)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if _WARNING_CODE_RE.fullmatch(normalized) is None:
            raise ValueError("Warning code must be a lowercase identifier")
        return normalized

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Warning message is required")
        return normalized


__all__ = [
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolExecutor",
    "RuntimeToolParser",
    "RuntimeToolSpec",
    "RuntimeToolWarning",
]
