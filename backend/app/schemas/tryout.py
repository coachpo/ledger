from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator

from app.schemas.common import CamelModel, ensure_timezone, normalize_runtime_inputs
from app.schemas.runtime import (
    ApprovalSummary,
    PersonaProfileRef,
    RuntimeRunStatus,
    TerminalError,
    TraceSummary,
)


def _normalize_required_text(value: object, *, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} is required")
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized


class TryoutExecute(CamelModel):
    workflow_spec_key: str | None = None
    workflow_spec_version: int | None = Field(default=None, ge=1)
    agent_spec_key: str | None = None
    agent_spec_version: int | None = Field(default=None, ge=1)
    inputs: dict[str, str] = Field(default_factory=dict)
    persona_profile_refs: list[PersonaProfileRef] = Field(default_factory=list)
    persist_run: bool = False

    @field_validator("workflow_spec_key", "agent_spec_key", mode="before")
    @classmethod
    def validate_optional_keys(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("inputs", mode="before")
    @classmethod
    def validate_inputs(cls, value: object) -> dict[str, str]:
        return normalize_runtime_inputs(value)

    @model_validator(mode="after")
    def validate_target(self) -> TryoutExecute:
        has_workflow_target = self.workflow_spec_key is not None
        has_agent_target = self.agent_spec_key is not None
        if has_workflow_target == has_agent_target:
            raise ValueError("Provide exactly one of workflowSpecKey or agentSpecKey")
        return self


class TryoutRead(CamelModel):
    run_id: int = Field(validation_alias=AliasChoices("run_id", "runId", "id"), ge=1)
    status: RuntimeRunStatus
    final_output: Any | None = None
    report_markdown: str | None = None
    trace_summary: TraceSummary
    approval_summary: ApprovalSummary
    expires_at: datetime | None = None
    terminal_error_code: str | None = Field(default=None, exclude=True)
    terminal_error_message: str | None = Field(default=None, exclude=True)

    @field_validator("report_markdown", mode="before")
    @classmethod
    def validate_report_markdown(cls, value: object) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("expires_at")
    @classmethod
    def validate_expires_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)

    @computed_field
    def terminal_error(self) -> TerminalError | None:
        if self.terminal_error_code is None or self.terminal_error_message is None:
            return None
        return TerminalError(code=self.terminal_error_code, message=self.terminal_error_message)


class TryoutPersistRead(TryoutRead):
    pass
