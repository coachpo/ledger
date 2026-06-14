from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal, Self, cast

from pydantic import Field, ValidationError, field_validator

from app.agents import get_default_tool_catalog
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec
from app.schemas.common import CamelModel, ensure_timezone
from app.schemas.memory import (
    MEMORY_LOOKUP_DEFAULT_LIMIT,
    MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS,
    MEMORY_LOOKUP_MAX_CHARACTERS,
    MEMORY_LOOKUP_MAX_LIMIT,
    MemoryPromptSnippet,
    MemoryProvenance,
    MemoryQuery,
    MemoryRevisionAction,
    MemoryRevisionPolicy,
    MemoryScope,
    MemoryScopeType,
    MemorySubjectRef,
    MemoryWriteRequest,
    MemoryWriteResult,
)
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.runtime_tool_grants import RuntimeToolGrantPolicy, RuntimeToolGrantService

MEMORY_WRITE_TOOL_KEY = "signaldeck.core.memory.write"
MEMORY_LOOKUP_TOOL_KEY = "signaldeck.core.memory.lookup"
MEMORY_WRITE_OPENAI_FUNCTION_NAME = "signaldeck_core_memory_write"
MEMORY_LOOKUP_OPENAI_FUNCTION_NAME = "signaldeck_core_memory_lookup"
MEMORY_TOOL_ACCESS_DENIED_CODE = "agent_execution_access_denied"
MEMORY_WRITE_ACCESS_DENIED_MESSAGE = "Agent is not authorized to use signaldeck.core.memory.write."
MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE = "Agent is not authorized to use signaldeck.core.memory.lookup."
MEMORY_WRITE_GRANT_POLICY = RuntimeToolGrantPolicy(
    tool_key=MEMORY_WRITE_TOOL_KEY,
    denied_code=MEMORY_TOOL_ACCESS_DENIED_CODE,
    denied_message=MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
)
MEMORY_LOOKUP_GRANT_POLICY = RuntimeToolGrantPolicy(
    tool_key=MEMORY_LOOKUP_TOOL_KEY,
    denied_code=MEMORY_TOOL_ACCESS_DENIED_CODE,
    denied_message=MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE,
)

_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {"auditLinks", "downloadUrl", "reportId", "reportName", "reportSlug", "url"}
)
_FORBIDDEN_TEXT_RE = re.compile(r"https?://\S+|/reports/\S*|\bdownload(?:url)?\b", re.I)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)]\([^)]+\)")
_MARKDOWN_PREFIX_RE = re.compile(r"^\s{0,3}(?:#{1,6}|[-*+>])\s+", re.MULTILINE)
_MEMORY_SCOPE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "scopeType": {
            "type": "string",
            "enum": ["package", "workflow", "run", "agent", "namespace"],
        },
        "scopeKey": {"type": "string", "minLength": 1, "maxLength": 160},
    },
    "required": ["scopeType", "scopeKey"],
    "additionalProperties": False,
}
_MEMORY_OPTIONAL_SCOPE_SCHEMA: dict[str, object] = {
    **_MEMORY_SCOPE_SCHEMA,
    "type": ["object", "null"],
}
_MEMORY_SUBJECT_REF_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "minLength": 1, "maxLength": 80},
        "id": {"type": "string", "minLength": 1, "maxLength": 160},
        "label": {"type": ["string", "null"], "maxLength": 160},
    },
    "required": ["kind", "id", "label"],
    "additionalProperties": False,
}
_MEMORY_WRITE_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "kind": {"type": ["string", "null"], "maxLength": 80},
        "summary": {"type": "string", "minLength": 1},
        "content": {"type": "string", "minLength": 1},
        "subjectRefs": {
            "type": ["array", "null"],
            "items": _MEMORY_SUBJECT_REF_INPUT_SCHEMA,
        },
        "scope": _MEMORY_SCOPE_SCHEMA,
        "idempotencyKey": {"type": ["string", "null"], "maxLength": 160},
        "supersedesRevisionId": {"type": ["string", "null"], "maxLength": 160},
    },
    "required": [
        "kind",
        "summary",
        "content",
        "subjectRefs",
        "scope",
        "idempotencyKey",
        "supersedesRevisionId",
    ],
    "additionalProperties": False,
}
_MEMORY_LOOKUP_PARAMETERS_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "query": {"type": ["string", "null"], "maxLength": 1000},
        "scope": _MEMORY_OPTIONAL_SCOPE_SCHEMA,
        "subjectRefs": {
            "type": ["array", "null"],
            "items": _MEMORY_SUBJECT_REF_INPUT_SCHEMA,
        },
        "kind": {"type": ["string", "null"], "maxLength": 80},
        "tags": {"type": ["array", "null"], "items": {"type": "string"}},
        "limit": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": MEMORY_LOOKUP_MAX_LIMIT,
        },
        "offset": {"type": ["integer", "null"], "minimum": 0},
        "maxCharacters": {
            "type": ["integer", "null"],
            "minimum": 1,
            "maximum": MEMORY_LOOKUP_MAX_CHARACTERS,
        },
    },
    "required": [
        "query",
        "scope",
        "subjectRefs",
        "kind",
        "tags",
        "limit",
        "offset",
        "maxCharacters",
    ],
    "additionalProperties": False,
}


class RuntimeMemorySubjectRefArguments(CamelModel):
    kind: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=160)
    label: str | None = Field(default=None, max_length=160)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _required_text(value).lower()

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _required_text(value)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> str | None:
        return _optional_text(value)

    def to_memory_subject_ref(self) -> MemorySubjectRef:
        return MemorySubjectRef(
            kind=self.kind,
            id=self.id,
            label=self.label,
            attributes={},
        )


class RuntimeMemoryWriteArguments(CamelModel):
    kind: str | None = Field(default=None, max_length=80)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[RuntimeMemorySubjectRefArguments] = Field(default_factory=list)
    scope: MemoryScope
    idempotency_key: str | None = Field(default=None, max_length=160)
    supersedes_revision_id: str | None = Field(default=None, max_length=160)

    @field_validator("kind", "idempotency_key", "supersedes_revision_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return _optional_text(value)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return _required_text(value)

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        return [] if value is None else value


class RuntimeMemoryLookupArguments(CamelModel):
    query: str | None = Field(default=None, max_length=1000)
    scope: MemoryScope | None = None
    subject_refs: list[RuntimeMemorySubjectRefArguments] = Field(default_factory=list)
    kind: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=MEMORY_LOOKUP_DEFAULT_LIMIT, ge=1, le=MEMORY_LOOKUP_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    max_characters: int = Field(
        default=MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS,
        ge=1,
        le=MEMORY_LOOKUP_MAX_CHARACTERS,
    )

    @field_validator("query", "kind", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return _optional_text(value)

    @field_validator("subject_refs", "tags", mode="before")
    @classmethod
    def coerce_lists(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("limit", mode="before")
    @classmethod
    def default_limit(cls, value: object) -> object:
        return MEMORY_LOOKUP_DEFAULT_LIMIT if value is None else value

    @field_validator("offset", mode="before")
    @classmethod
    def default_offset(cls, value: object) -> object:
        return 0 if value is None else value

    @field_validator("max_characters", mode="before")
    @classmethod
    def default_max_characters(cls, value: object) -> object:
        return MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS if value is None else value

    def _selected_scope(self) -> MemoryScope | None:
        return self.scope

    def to_query(self) -> MemoryQuery:
        return MemoryQuery(
            query=self.query,
            scope=self._selected_scope(),
            subject_refs=[ref.to_memory_subject_ref() for ref in self.subject_refs],
            kind=self.kind,
            tags=self.tags,
            limit=self.limit,
            offset=self.offset,
            max_characters=self.max_characters,
        )


class RuntimeMemoryWriteResult(CamelModel):
    tool_key: Literal["signaldeck.core.memory.write"] = "signaldeck.core.memory.write"
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    visible_to_workflow: bool
    revision_action: MemoryRevisionAction
    created_at: datetime
    provenance: MemoryProvenance
    warnings: list[dict[str, object]] = Field(default_factory=list)

    @classmethod
    def from_memory_write_result(cls, result: MemoryWriteResult) -> Self:
        return cls(
            memory_id=result.memory_id,
            revision_id=result.revision_id,
            visible_to_workflow=result.visible_to_workflow,
            revision_action=result.revision_action,
            created_at=result.created_at,
            provenance=result.provenance,
            warnings=_model_safe_list(result.warnings),
        )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeMemoryLookupItem(CamelModel):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[dict[str, object]] = Field(default_factory=list)
    attributes: dict[str, object] = Field(default_factory=dict)
    scope: MemoryScope
    provenance: MemoryProvenance
    created_at: datetime

    @classmethod
    def from_snippet(cls, snippet: MemoryPromptSnippet) -> Self:
        return cls(
            memory_id=snippet.memory_id,
            revision_id=snippet.revision_id,
            kind=snippet.kind,
            summary=_model_safe_text(snippet.summary),
            content=_model_safe_text(snippet.content),
            subject_refs=[_subject_ref_payload(ref) for ref in snippet.subject_refs],
            attributes={},
            scope=snippet.scope,
            provenance=snippet.provenance,
            created_at=snippet.created_at,
        )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class RuntimeMemoryLookupResult(CamelModel):
    tool_key: Literal["signaldeck.core.memory.lookup"] = "signaldeck.core.memory.lookup"
    scope_mode: Literal["explicit-selectors", "current-context-fallback"]
    fallback_scope: Literal["current-run-package-agent"]
    limit: int
    max_characters: int
    count: int
    memories: list[RuntimeMemoryLookupItem]
    warnings: list[dict[str, object]] = Field(default_factory=list)

    @classmethod
    def from_snippets(cls, query: MemoryQuery, snippets: list[MemoryPromptSnippet]) -> Self:
        memories = [RuntimeMemoryLookupItem.from_snippet(snippet) for snippet in snippets]
        return cls(
            scope_mode=query.scope_mode,
            fallback_scope=query.fallback_scope,
            limit=query.limit,
            max_characters=query.max_characters,
            count=len(memories),
            memories=memories,
        )


def parse_memory_write_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "kind",
            "summary",
            "content",
            "subjectRefs",
            "scope",
            "idempotencyKey",
            "supersedesRevisionId",
        },
        function_name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    )
    try:
        payload = RuntimeMemoryWriteArguments.model_validate(raw_arguments)
    except ValidationError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="signaldeck_core_memory_write arguments failed validation.",
            details=_validation_details_from_pydantic_error(exc),
        ) from exc
    return {"payload": payload}


def execute_memory_write(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    payload = cast(RuntimeMemoryWriteArguments, arguments["payload"])
    provenance = _trusted_memory_provenance(
        context,
        function_name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    )
    lookup_context = _lookup_context(context)
    write_request = MemoryWriteRequest(
        kind=payload.kind or "memory",
        summary=payload.summary,
        content=payload.content,
        subject_refs=[ref.to_memory_subject_ref() for ref in payload.subject_refs],
        attributes={},
        scope=_selected_write_scope(payload, lookup_context),
        provenance=provenance,
        revision=MemoryRevisionPolicy(
            supersedes_revision_id=payload.supersedes_revision_id,
        ),
        idempotency_key=payload.idempotency_key,
    )
    with context.session_factory() as session:
        result = MemoryService(
            session,
            current_context=lookup_context,
        ).write_memory(
            capability_references=context.capability_references,
            payload=write_request,
            grant_policy=MEMORY_WRITE_GRANT_POLICY,
        )
    return cast(
        dict[str, object],
        RuntimeMemoryWriteResult.from_memory_write_result(result).model_dump(
            mode="json",
            by_alias=True,
        ),
    )


def parse_memory_lookup_arguments(arguments_json: str) -> dict[str, object]:
    raw_arguments = _parse_json_object(
        arguments_json,
        function_name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    _reject_unexpected_keys(
        raw_arguments,
        allowed_keys={
            "query",
            "scope",
            "subjectRefs",
            "kind",
            "tags",
            "limit",
            "offset",
            "maxCharacters",
        },
        function_name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    )
    try:
        payload = RuntimeMemoryLookupArguments.model_validate(raw_arguments)
    except ValidationError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message="signaldeck_core_memory_lookup arguments failed validation.",
            details=_validation_details_from_pydantic_error(exc),
        ) from exc
    return {"payload": payload}


def execute_memory_lookup(
    context: RuntimeToolContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    payload = cast(RuntimeMemoryLookupArguments, arguments["payload"])
    query = payload.to_query()
    lookup_context = _lookup_context(context)
    if _uses_current_context_fallback(query) and not lookup_context.has_values():
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=(
                "signaldeck_core_memory_lookup requires at least one explicit selector or "
                "current runtime context."
            ),
        )
    with context.session_factory() as session:
        RuntimeToolGrantService(get_default_tool_catalog()).require_runtime_tool_grant(
            capability_references=context.capability_references,
            grant_policy=MEMORY_LOOKUP_GRANT_POLICY,
        )
        service = MemoryService(
            session,
            current_context=lookup_context,
        )
        snippets = service.query_memory(query)
        result_payload = cast(
            dict[str, object],
            RuntimeMemoryLookupResult.from_snippets(query, snippets).model_dump(
                mode="json",
                by_alias=True,
            ),
        )
        service.record_injection_event(
            snippets=snippets,
            injected_text=json.dumps(result_payload, sort_keys=True),
            filters={
                "toolKey": MEMORY_LOOKUP_TOOL_KEY,
                "functionName": MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
                "scopeMode": query.scope_mode,
            },
            budget={
                "limit": query.limit,
                "offset": query.offset,
                "maxCharacters": query.max_characters,
            },
            retrieval_mode="runtime-tool",
        )
    return result_payload


def _parse_json_object(arguments_json: str, *, function_name: str) -> dict[str, object]:
    try:
        raw_payload = cast(object, json.loads(arguments_json))
    except json.JSONDecodeError as exc:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"OpenAI response requested {function_name} with invalid JSON arguments.",
        ) from exc
    if not isinstance(raw_payload, dict):
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=f"{function_name} arguments must be a JSON object.",
        )
    return cast(dict[str, object], raw_payload)


def _reject_unexpected_keys(
    raw_arguments: dict[str, object],
    *,
    allowed_keys: set[str],
    function_name: str,
) -> None:
    unexpected_keys = sorted(set(raw_arguments) - allowed_keys)
    if unexpected_keys:
        raise RuntimeToolError(
            code="agent_tool_call_invalid",
            message=(
                f"{function_name} arguments contained unsupported fields: "
                f"{', '.join(unexpected_keys)}"
            ),
        )


def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(str(part) for part in location) if location else "input"
        details.append(
            {
                "field": field or "input",
                "issue": str(error.get("msg", "Invalid value")),
            }
        )
    return details


def _trusted_memory_provenance(
    context: RuntimeToolContext,
    *,
    function_name: str,
) -> MemoryProvenance:
    missing_fields: list[str] = []
    if context.run_id is None:
        missing_fields.append("runId")
    if context.agent_key is None:
        missing_fields.append("agentKey")
    if context.agent_version is None:
        missing_fields.append("agentVersion")
    if missing_fields:
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=(
                f"{function_name} requires runtime context fields: {', '.join(missing_fields)}."
            ),
        )
    assert context.run_id is not None
    assert context.agent_key is not None
    assert context.agent_version is not None
    workflow_key = context.workflow_key
    workflow_version = context.workflow_version
    if context.package_ownership is not None:
        workflow_key = context.package_ownership.workflow_key
    return MemoryProvenance(
        run_id=context.run_id,
        agent_key=context.agent_key,
        agent_version=context.agent_version,
        agent_name=context.agent_name,
        workflow_key=workflow_key,
        workflow_version=workflow_version,
        step_id=context.step_id,
        slot=context.slot,
        trace_id=context.trace_id,
    )


def _selected_write_scope(
    payload: RuntimeMemoryWriteArguments,
    lookup_context: MemoryLookupContext,
) -> MemoryScope:
    scope = payload.scope
    if scope.scope_type == MemoryScopeType.RUN and lookup_context.run_id is None:
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message="signaldeck_core_memory_write requires run runtime context for run memory scope.",
        )
    if (
        scope.scope_type
        in {
            MemoryScopeType.PACKAGE,
            MemoryScopeType.WORKFLOW,
            MemoryScopeType.AGENT,
        }
        and lookup_context.package_key is None
    ):
        raise RuntimeToolError(
            code="agent_tool_dependency_missing",
            message=(
                "signaldeck_core_memory_write requires package runtime ownership for "
                "package, workflow, or agent memory scopes."
            ),
        )
    return scope


def _lookup_context(context: RuntimeToolContext) -> MemoryLookupContext:
    package_key = None
    workflow_key = context.workflow_key
    if context.package_ownership is not None:
        package_key = context.package_ownership.package_key
        workflow_key = context.package_ownership.workflow_key
    return MemoryLookupContext(
        run_id=context.run_id,
        package_key=package_key,
        workflow_key=workflow_key,
        agent_key=context.agent_key,
        run_step_id=context.run_step_id,
        run_agent_invocation_id=context.run_agent_invocation_id,
        run_operation_invocation_id=context.run_operation_invocation_id,
        step_id=context.step_id,
        invocation_id=context.invocation_id,
        trace_span_id=context.trace_span_id or context.trace_id,
    )


def _uses_current_context_fallback(query: MemoryQuery) -> bool:
    return query.scope_mode == "current-context-fallback"


def _required_text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Value is required")
    return normalized


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
    normalized = value.strip()
    return normalized or None


def _subject_ref_payload(ref: MemorySubjectRef) -> dict[str, object]:
    payload = cast(
        dict[str, object],
        ref.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    attributes = payload.get("attributes")
    if isinstance(attributes, Mapping):
        safe_attributes = _model_safe_mapping(attributes)
        if safe_attributes:
            payload["attributes"] = safe_attributes
        else:
            _ = payload.pop("attributes", None)
    return _model_safe_mapping(payload)


def _model_safe_mapping(value: Mapping[Any, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        if key in _FORBIDDEN_OUTPUT_KEYS:
            continue
        safe_value = _model_safe_value(raw_value)
        if safe_value is not None:
            payload[key] = safe_value
    return payload


def _model_safe_list(value: Sequence[object]) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            safe_item = _model_safe_mapping(item)
            if safe_item:
                items.append(safe_item)
    return items


def _model_safe_value(value: object) -> object | None:
    if isinstance(value, str):
        return _model_safe_text(value)
    if isinstance(value, Mapping):
        return _model_safe_mapping(value)
    if isinstance(value, list):
        return [_model_safe_value(item) for item in value]
    if isinstance(value, int | float | bool) or value is None:
        return value
    return str(value)


def _model_safe_text(value: str) -> str:
    text = _MARKDOWN_LINK_RE.sub(r"\1", value)
    text = _MARKDOWN_PREFIX_RE.sub("", text)
    text = text.replace("`", "")
    text = _FORBIDDEN_TEXT_RE.sub("[redacted]", text)
    normalized = text.strip()
    return normalized or "[redacted]"


_MEMORY_WRITE_DESCRIPTION = "Write a bounded, platform-core memory entry for this run."
_MEMORY_WRITE_GUIDANCE = (
    "When a durable, platform-neutral memory should be persisted, call "
    "signaldeck_core_memory_write with kind, summary, content, optional subjectRefs, "
    "optional private scope, and idempotencyKey. Do not include report ids, "
    "report slugs, URLs, downloads, trusted run/agent fields, or free-form metadata maps."
)
_MEMORY_LOOKUP_DESCRIPTION = (
    "Look up bounded, scoped platform-core memory snippets for the current run context."
)
_MEMORY_LOOKUP_GUIDANCE = (
    "When historical SignalDeck memory is needed, call signaldeck_core_memory_lookup "
    "with explicit private scope, subjectRefs, or kind. If no selector "
    "is provided, the server restricts lookup to the current run, package, "
    "workflow, and agent context. Keep limit at or below 20 and maxCharacters "
    "at or below 8000."
)

MEMORY_WRITE_TOOL_SPEC = RuntimeToolSpec(
    key=MEMORY_WRITE_TOOL_KEY,
    openai_function_name=MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    display_name="Memory Write",
    description=_MEMORY_WRITE_DESCRIPTION,
    parameters_schema=_MEMORY_WRITE_PARAMETERS_SCHEMA,
    guidance=_MEMORY_WRITE_GUIDANCE,
    sort_order=5,
    denied_code=MEMORY_TOOL_ACCESS_DENIED_CODE,
    denied_message=MEMORY_WRITE_ACCESS_DENIED_MESSAGE,
    parser=parse_memory_write_arguments,
    executor=execute_memory_write,
)

MEMORY_LOOKUP_TOOL_SPEC = RuntimeToolSpec(
    key=MEMORY_LOOKUP_TOOL_KEY,
    openai_function_name=MEMORY_LOOKUP_OPENAI_FUNCTION_NAME,
    display_name="Memory Lookup",
    description=_MEMORY_LOOKUP_DESCRIPTION,
    parameters_schema=_MEMORY_LOOKUP_PARAMETERS_SCHEMA,
    guidance=_MEMORY_LOOKUP_GUIDANCE,
    sort_order=6,
    denied_code=MEMORY_TOOL_ACCESS_DENIED_CODE,
    denied_message=MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE,
    parser=parse_memory_lookup_arguments,
    executor=execute_memory_lookup,
)

CORE_MEMORY_RUNTIME_TOOL_SPECS: tuple[RuntimeToolSpec, ...] = (
    MEMORY_WRITE_TOOL_SPEC,
    MEMORY_LOOKUP_TOOL_SPEC,
)

__all__ = [
    "CORE_MEMORY_RUNTIME_TOOL_SPECS",
    "MEMORY_LOOKUP_ACCESS_DENIED_MESSAGE",
    "MEMORY_LOOKUP_GRANT_POLICY",
    "MEMORY_LOOKUP_OPENAI_FUNCTION_NAME",
    "MEMORY_LOOKUP_TOOL_KEY",
    "MEMORY_LOOKUP_TOOL_SPEC",
    "MEMORY_TOOL_ACCESS_DENIED_CODE",
    "MEMORY_WRITE_ACCESS_DENIED_MESSAGE",
    "MEMORY_WRITE_GRANT_POLICY",
    "MEMORY_WRITE_OPENAI_FUNCTION_NAME",
    "MEMORY_WRITE_TOOL_KEY",
    "MEMORY_WRITE_TOOL_SPEC",
    "RuntimeMemoryLookupArguments",
    "RuntimeMemoryLookupItem",
    "RuntimeMemoryLookupResult",
    "RuntimeMemoryWriteArguments",
    "RuntimeMemoryWriteResult",
    "execute_memory_lookup",
    "execute_memory_write",
    "parse_memory_lookup_arguments",
    "parse_memory_write_arguments",
]
