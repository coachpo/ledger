from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.models.mcp_server import EncryptedJSONB

_MODEL_CONNECTION_DEFAULT_CAPABILITIES = {
    "textGeneration": {"status": "supported", "detail": None, "lastProbedAt": None},
    "chatCompletions": {"status": "notApplicable", "detail": None, "lastProbedAt": None},
    "responsesApi": {"status": "supported", "detail": None, "lastProbedAt": None},
    "streaming": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "nativeToolCalls": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "parallelToolCalls": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "jsonObjectOutput": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "strictJsonSchemaOutput": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "reasoningHints": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "usageReporting": {"status": "unknown", "detail": None, "lastProbedAt": None},
    "systemMessages": {"status": "unknown", "detail": None, "lastProbedAt": None},
}
_MODEL_CONNECTION_DEFAULT_CAPABILITIES_JSON = json.dumps(
    _MODEL_CONNECTION_DEFAULT_CAPABILITIES,
    sort_keys=True,
)
_PROTOCOL_PROFILE_TO_LEGACY_API_STYLE = {
    "openai_chat_completions": "chat_completions",
    "openai_responses": "responses",
}
_LEGACY_API_STYLE_TO_PROTOCOL_PROFILE = {
    api_style: protocol_profile
    for protocol_profile, api_style in _PROTOCOL_PROFILE_TO_LEGACY_API_STYLE.items()
}


def _default_capabilities_payload() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(_MODEL_CONNECTION_DEFAULT_CAPABILITIES_JSON))


class ModelConnection(IdMixin, TimestampMixin, Base):
    __tablename__ = "model_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active')",
            name="ck_model_connections_status",
        ),
        CheckConstraint(
            "reasoning_effort IS NULL OR (length(btrim(reasoning_effort)) BETWEEN 1 AND 128)",
            name="ck_model_connections_reasoning_effort",
        ),
        CheckConstraint(
            "protocol_profile IN ('openai_chat_completions', 'openai_responses')",
            name="ck_model_connections_protocol_profile",
        ),
        CheckConstraint(
            "jsonb_typeof(capabilities) = 'object' AND NOT jsonb_path_exists("
            'capabilities, \'$.*.status ? (!(@ == "supported" || @ == "unsupported" '
            '|| @ == "unknown" || @ == "notApplicable"))\')',
            name="ck_model_connections_capability_statuses",
        ),
        CheckConstraint(
            "output_strategy_policy IN ("
            "'require_strict_schema', 'prefer_strict_schema', "
            "'allow_json_object_validation', 'allow_plain_text')",
            name="ck_model_connections_output_strategy_policy",
        ),
        CheckConstraint(
            "parallel_tool_calls_policy IN ('allow', 'serialize', 'forbid')",
            name="ck_model_connections_parallel_tool_calls_policy",
        ),
        CheckConstraint(
            "reasoning_policy IN ('allow', 'forbid')",
            name="ck_model_connections_reasoning_policy",
        ),
        CheckConstraint(
            "streaming_policy IN ('allow', 'forbid')",
            name="ck_model_connections_streaming_policy",
        ),
        CheckConstraint(
            "probe_cache_ttl_seconds > 0",
            name="ck_model_connections_probe_cache_ttl_positive",
        ),
        CheckConstraint(
            "timeout_seconds > 0",
            name="ck_model_connections_timeout_seconds_positive",
        ),
        UniqueConstraint("key", name="uq_model_connections_key"),
        Index("ix_model_connections_key", "key"),
        Index("ix_model_connections_status", "status"),
        Index("ix_model_connections_model_id", "model_id"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="active",
        server_default="active",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    reasoning_effort: Mapped[str | None] = mapped_column(
        String(128).evaluates_none(),
        nullable=True,
        default="medium",
        server_default="medium",
    )
    protocol_profile: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="openai_responses",
        server_default="openai_responses",
    )
    capabilities: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=_default_capabilities_payload,
        server_default=sql_text(f"'{_MODEL_CONNECTION_DEFAULT_CAPABILITIES_JSON}'::jsonb"),
    )
    output_strategy_policy: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="prefer_strict_schema",
        server_default="prefer_strict_schema",
    )
    parallel_tool_calls_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="serialize",
        server_default="serialize",
    )
    reasoning_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="allow",
        server_default="allow",
    )
    streaming_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="allow",
        server_default="allow",
    )
    last_probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    probe_cache_ttl_seconds: Mapped[int] = mapped_column(
        nullable=False,
        default=900,
        server_default="900",
    )
    timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=60, server_default="60")
    secret_payload: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def api_style(self) -> str:
        return _PROTOCOL_PROFILE_TO_LEGACY_API_STYLE.get(
            self.protocol_profile,
            "responses",
        )

    @api_style.setter
    def api_style(self, value: str) -> None:
        self.protocol_profile = _LEGACY_API_STYLE_TO_PROTOCOL_PROFILE.get(
            str(value).strip(),
            "openai_responses",
        )
