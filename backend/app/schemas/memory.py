from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Final, Literal, Self, cast

from fastapi import status
from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from app.core.errors import ApiError
from app.schemas.common import CamelModel, ensure_timezone

INVALID_MEMORY_ID_CODE: Final = "invalid_memory_id"
MEMORY_NOT_FOUND_CODE: Final = "memory_not_found"
MEMORY_NAMESPACE_ACCESS_DENIED_CODE: Final = "memory_namespace_access_denied"
MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE: Final = "Memory namespace access denied."
MEMORY_NAMESPACE_SCOPE_SEPARATOR: Final = "/"

MemoryProjection = Literal["model-visible", "api-visible", "ui-visible"]
MemoryNamespaceAction = Literal["read", "write"]

MEMORY_LOOKUP_DEFAULT_LIMIT: Final = 5
MEMORY_LOOKUP_MAX_LIMIT: Final = 20
MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS: Final = 4_000
MEMORY_LOOKUP_MAX_CHARACTERS: Final = 8_000
MEMORY_API_MAX_REVISIONS: Final = 50
MEMORY_API_MAX_EVENTS: Final = 100
MEMORY_LOOKUP_CURRENT_CONTEXT_FALLBACK: Final = "current-run-package-agent"
MEMORY_REVISION_WRITE_MODE: Final = "immutable-revision-per-content-change"
MEMORY_DUPLICATE_REVISION_BEHAVIOR: Final = "reuse-existing-active-revision"
MEMORY_DEFERRED_GET_DECISION: Final = "phase-1b"
MEMORY_CORE_RUNTIME_TOOL_KEYS: Final[tuple[str, str]] = (
    "signaldeck.memory.write",
    "signaldeck.memory.lookup",
)
MEMORY_IDEMPOTENCY_FALLBACK_FIELDS: Final[tuple[str, ...]] = (
    "scope_type",
    "scope_key",
    "kind",
    "content_hash",
    "source_run_id",
    "source_agent_key",
    "source_step_id",
    "source_slot",
)
MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "reportId",
        "reportSlug",
        "reportName",
        "url",
        "downloadUrl",
        "auditLinks",
        "outcome",
        "reflections",
    }
)
MEMORY_PROJECTION_MATRIX: Final[dict[MemoryProjection, tuple[str, ...]]] = {
    "model-visible": (
        "memoryId",
        "revisionId",
        "kind",
        "summary",
        "content",
        "subjectRefs",
        "attributes",
        "scope",
        "provenance",
        "warnings",
    ),
    "api-visible": (
        "memoryId",
        "revisionId",
        "visibleToWorkflow",
        "kind",
        "summary",
        "content",
        "subjectRefs",
        "attributes",
        "scope",
        "provenance",
        "revision",
        "createdAt",
        "updatedAt",
    ),
    "ui-visible": (
        "memoryId",
        "revisionId",
        "visibleToWorkflow",
        "kind",
        "summary",
        "subjectRefs",
        "scope",
        "provenance",
        "createdAt",
        "updatedAt",
    ),
}

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonScalar] | dict[str, JsonScalar]
type MemoryAttributes = dict[str, JsonValue]

_MEMORY_COMPATIBILITY_EXCLUDE: Final[set[str]] = {
    "outcome",
    "reflections",
}
_NAMESPACE_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


def invalid_memory_id_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=INVALID_MEMORY_ID_CODE,
        message="Invalid memory id",
    )


def memory_not_found_error() -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code=MEMORY_NOT_FOUND_CODE,
        message="Memory not found",
    )


def _normalize_required_text(
    value: object,
    *,
    field_name: str,
    max_length: int | None = None,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if max_length is not None and len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _normalize_optional_text(
    value: object,
    *,
    field_name: str,
    max_length: int | None = None,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        return None
    if max_length is not None and len(normalized) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return normalized


def _normalize_namespace_key(value: object, *, field_name: str) -> str:
    normalized = _normalize_required_text(value, field_name=field_name, max_length=120)
    if "*" in normalized:
        raise ValueError(f"{field_name} does not support wildcards")
    if _NAMESPACE_KEY_RE.fullmatch(normalized) is None:
        raise ValueError(
            f"{field_name} must start with a lowercase letter and use only lowercase "
            "letters, numbers, and underscores"
        )
    return normalized


def _normalize_namespace_actions(value: object) -> tuple[MemoryNamespaceAction, ...]:
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("actions must be an array of read/write values")
    actions: list[MemoryNamespaceAction] = []
    for item in cast(list[object] | tuple[object, ...] | set[object], value):
        if not isinstance(item, str):
            raise ValueError("actions must be an array of read/write values")
        normalized = item.strip().lower()
        if normalized not in {"read", "write"}:
            raise ValueError("actions may only contain read or write")
        action = cast(MemoryNamespaceAction, normalized)
        if action not in actions:
            actions.append(action)
    if not actions:
        raise ValueError("actions must include read or write")
    return tuple(actions)


def _normalize_kind(value: object, *, field_name: str = "kind") -> str:
    normalized = _normalize_required_text(value, field_name=field_name, max_length=80)
    return normalized.lower()


def _normalize_optional_kind(value: object, *, field_name: str = "kind") -> str | None:
    normalized = _normalize_optional_text(value, field_name=field_name, max_length=80)
    return None if normalized is None else normalized.lower()


def _normalize_attributes(value: object) -> MemoryAttributes:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("attributes must be an object")
    raw_attributes = cast(dict[object, JsonValue], value)
    normalized: MemoryAttributes = {}
    for raw_key, raw_value in raw_attributes.items():
        key = _normalize_required_text(raw_key, field_name="Attribute key", max_length=120)
        normalized[key] = raw_value
    return normalized


def _normalize_idempotency_fallback_fields(value: object) -> tuple[str, ...]:
    if value is None:
        return MEMORY_IDEMPOTENCY_FALLBACK_FIELDS
    if not isinstance(value, (list, tuple)):
        raise ValueError("idempotencyFallbackFields must be a list of field names")
    raw_fields = cast(list[object] | tuple[object, ...], value)
    fields: list[str] = []
    for item in raw_fields:
        if not isinstance(item, str):
            raise ValueError("idempotencyFallbackFields must be a list of field names")
        fields.append(item)
    normalized = tuple(fields)
    if normalized != MEMORY_IDEMPOTENCY_FALLBACK_FIELDS:
        raise ValueError("idempotencyFallbackFields must use the phase-1 fallback identity")
    return normalized


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class MemoryScopeType(str, Enum):  # noqa: UP042
    PACKAGE = "package"
    WORKFLOW = "workflow"
    RUN = "run"
    AGENT = "agent"
    NAMESPACE = "namespace"


class MemoryNamespaceSelector(CamelModel):
    owner_package_key: str = Field(min_length=1, max_length=120)
    namespace_key: str = Field(min_length=1, max_length=120)

    @field_validator("owner_package_key", mode="before")
    @classmethod
    def validate_owner_package_key(cls, value: object) -> str:
        return _normalize_namespace_key(value, field_name="ownerPackageKey")

    @field_validator("namespace_key", mode="before")
    @classmethod
    def validate_namespace_key(cls, value: object) -> str:
        return _normalize_namespace_key(value, field_name="namespaceKey")

    @model_validator(mode="after")
    def validate_qualified_key_length(self) -> Self:
        if len(self.qualified_key) > 160:
            raise ValueError("Namespace identity must be at most 160 characters")
        return self

    @property
    def qualified_key(self) -> str:
        return f"{self.owner_package_key}{MEMORY_NAMESPACE_SCOPE_SEPARATOR}{self.namespace_key}"

    def to_scope(self) -> MemoryScope:
        return MemoryScope(scope_type=MemoryScopeType.NAMESPACE, scope_key=self.qualified_key)

    @classmethod
    def from_scope_key(cls, scope_key: str) -> Self:
        if MEMORY_NAMESPACE_SCOPE_SEPARATOR not in scope_key:
            raise ValueError("Namespace scope keys must use ownerPackageKey/namespaceKey")
        owner_package_key, namespace_key = scope_key.split(MEMORY_NAMESPACE_SCOPE_SEPARATOR, 1)
        return cls(owner_package_key=owner_package_key, namespace_key=namespace_key)

    @classmethod
    def from_scope(cls, scope: MemoryScope) -> Self:
        if scope.scope_type != MemoryScopeType.NAMESPACE:
            raise ValueError("Memory scope is not a namespace scope")
        return cls.from_scope_key(scope.scope_key)


class MemoryNamespaceGrantSubject(CamelModel):
    package_key: str = Field(min_length=1, max_length=120)
    workflow_key: str | None = Field(default=None, max_length=120)
    agent_key: str | None = Field(default=None, max_length=120)

    @field_validator("package_key", mode="before")
    @classmethod
    def validate_package_key(cls, value: object) -> str:
        return _normalize_namespace_key(value, field_name="subject.packageKey")

    @field_validator("workflow_key", "agent_key", mode="before")
    @classmethod
    def validate_optional_subject_key(cls, value: object) -> str | None:
        if value is None:
            return None
        return _normalize_namespace_key(value, field_name="subject ref")

    def matches(
        self,
        *,
        package_key: str | None,
        workflow_key: str | None,
        agent_key: str | None,
    ) -> bool:
        if package_key != self.package_key:
            return False
        if self.workflow_key is not None and workflow_key != self.workflow_key:
            return False
        if self.agent_key is not None and agent_key != self.agent_key:
            return False
        return True


class MemoryNamespaceGrant(CamelModel):
    namespace: MemoryNamespaceSelector
    subject: MemoryNamespaceGrantSubject
    actions: tuple[MemoryNamespaceAction, ...] = Field(min_length=1, max_length=2)

    @field_validator("actions", mode="before")
    @classmethod
    def validate_actions(cls, value: object) -> tuple[MemoryNamespaceAction, ...]:
        return _normalize_namespace_actions(value)

    def allows(
        self,
        namespace: MemoryNamespaceSelector,
        action: MemoryNamespaceAction,
        *,
        package_key: str | None,
        workflow_key: str | None,
        agent_key: str | None,
    ) -> bool:
        return (
            self.namespace == namespace
            and action in self.actions
            and self.subject.matches(
                package_key=package_key,
                workflow_key=workflow_key,
                agent_key=agent_key,
            )
        )


class MemoryRevisionAction(str, Enum):  # noqa: UP042
    CREATED = "created"
    REUSED = "reused"
    SUPERSEDED = "superseded"


class MemoryId(CamelModel):
    value: str

    @field_validator("value", mode="before")
    @classmethod
    def validate_value(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="memoryId")


class MemoryScope(CamelModel):
    scope_type: MemoryScopeType
    scope_key: str = Field(min_length=1, max_length=160)

    @field_validator("scope_key", mode="before")
    @classmethod
    def validate_scope_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="scopeKey", max_length=160)

    @model_validator(mode="after")
    def validate_namespace_scope_key(self) -> Self:
        if self.scope_type == MemoryScopeType.NAMESPACE:
            _ = MemoryNamespaceSelector.from_scope_key(self.scope_key)
        return self


class MemorySubjectRef(CamelModel):
    kind: str = Field(min_length=1, max_length=80)
    id: str = Field(min_length=1, max_length=160)
    label: str | None = Field(default=None, max_length=160)
    attributes: MemoryAttributes = Field(default_factory=dict)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value, field_name="subjectRef.kind")

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="subjectRef.id", max_length=160)

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="subjectRef.label", max_length=160)

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)


class MemoryRevisionPolicy(CamelModel):
    mode: Literal["immutable-revision-per-content-change"] = MEMORY_REVISION_WRITE_MODE
    duplicate_content: Literal["reuse-existing-active-revision"] = (
        MEMORY_DUPLICATE_REVISION_BEHAVIOR
    )
    supersedes_revision_id: str | None = Field(default=None, max_length=160)

    @field_validator("supersedes_revision_id", mode="before")
    @classmethod
    def normalize_supersedes_revision_id(cls, value: object) -> str | None:
        return _normalize_optional_text(
            value,
            field_name="supersedesRevisionId",
            max_length=160,
        )


class MemoryRevisionRead(CamelModel):
    revision_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime
    supersedes_revision_id: str | None = Field(default=None, max_length=160)

    @field_validator("revision_id", "content_hash", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Revision field", max_length=160)

    @field_validator("supersedes_revision_id", mode="before")
    @classmethod
    def normalize_supersedes_revision_id(cls, value: object) -> str | None:
        return _normalize_optional_text(
            value,
            field_name="supersedesRevisionId",
            max_length=160,
        )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryProvenance(CamelModel):
    run_id: int = Field(ge=1)
    agent_key: str = Field(min_length=1, max_length=120)
    agent_version: int = Field(ge=1)
    created_by_type: Literal["agent", "operator"] = "agent"
    agent_name: str | None = Field(default=None, max_length=160)
    workflow_key: str | None = Field(default=None, max_length=120)
    workflow_version: int | None = Field(default=None, ge=1)
    step_id: str | None = Field(default=None, max_length=120)
    slot: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=255)

    @field_validator("agent_key", mode="before")
    @classmethod
    def validate_agent_key(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="agentKey", max_length=120)

    @field_validator("agent_name", "workflow_key", "step_id", "slot", "trace_id", mode="before")
    @classmethod
    def normalize_optional_text_fields(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Provenance field", max_length=255)


class MemoryContent(CamelModel):
    summary: str = Field(default="Memory content", min_length=1)
    content: str = Field(default="Memory content", min_length=1)
    attributes: MemoryAttributes = Field(default_factory=dict)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory content")

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)


class MemoryOutcome(CamelModel):
    summary: str = Field(default="Memory visibility recorded", min_length=1)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attributes: MemoryAttributes = Field(default_factory=dict)

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Outcome summary")

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)


class MemoryReflection(MemoryContent):
    reflected_at: datetime
    source: str | None = None
    reflection: str = ""

    @model_validator(mode="before")
    @classmethod
    def populate_neutral_reflection(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        reflection = _normalize_optional_text(payload.get("reflection"), field_name="reflection")
        if "summary" not in payload:
            payload["summary"] = reflection or "Memory reflection"
        if "content" not in payload:
            payload["content"] = reflection or payload["summary"]
        return payload

    @field_validator("source", mode="before")
    @classmethod
    def normalize_source(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Reflection source", max_length=160)

    @field_validator("reflected_at")
    @classmethod
    def validate_reflected_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


def _default_memory_scope() -> MemoryScope:
    return MemoryScope(scope_type=MemoryScopeType.RUN, scope_key="run")


def _default_memory_revision() -> MemoryRevisionRead:
    return MemoryRevisionRead(
        revision_id="rev",
        version=1,
        content_hash=_content_hash(""),
        created_at=datetime.now(UTC),
    )


def _default_memory_outcome() -> MemoryOutcome:
    return MemoryOutcome(summary="Memory visibility recorded")


class MemoryAuditReportLink(CamelModel):
    reference: str = Field(default="audit-reference", min_length=1, max_length=255)
    label: str | None = Field(default=None, max_length=160)
    slug: str | None = Field(default=None, max_length=160)
    name: str | None = Field(default=None, max_length=160)
    url: str | None = Field(default=None, max_length=255)
    download_url: str | None = Field(default=None, max_length=255)

    @model_validator(mode="before")
    @classmethod
    def populate_reference(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        if "reference" not in payload:
            payload["reference"] = payload.get("slug") or payload.get("url") or payload.get("name")
        if "label" not in payload:
            payload["label"] = payload.get("name")
        return payload

    @field_validator("reference", mode="before")
    @classmethod
    def validate_reference(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Audit reference", max_length=255)

    @field_validator("label", "slug", "name", "url", "download_url", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Audit link field", max_length=255)


class MemoryAuditLinks(CamelModel):
    references: list[MemoryAuditReportLink] = Field(default_factory=list)
    report: MemoryAuditReportLink | None = None

    @field_validator("references", mode="before")
    @classmethod
    def coerce_references(cls, value: object) -> object:
        if value is None:
            return []
        return value


class _MemoryProjectionMixin(CamelModel):
    @model_serializer(mode="wrap")
    def serialize_without_compatibility_fields(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = cast(dict[str, object], handler(self))
        _ = payload.pop("action", None)
        if payload.get("auditLinks") is None:
            _ = payload.pop("auditLinks", None)
        if payload.get("audit_links") is None:
            _ = payload.pop("audit_links", None)
        return payload

    def model_visible_dump(self) -> dict[str, object]:
        return cast(
            dict[str, object],
            self.model_dump(
                mode="json",
                by_alias=True,
                exclude=_MEMORY_COMPATIBILITY_EXCLUDE | {"audit_links", "visible_to_workflow"},
                exclude_none=True,
            ),
        )

    def dump_for_projection(self, projection: MemoryProjection) -> dict[str, object]:
        if projection == "model-visible":
            return self.model_visible_dump()
        return cast(
            dict[str, object],
            self.model_dump(
                mode="json",
                by_alias=True,
                exclude=_MEMORY_COMPATIBILITY_EXCLUDE,
                exclude_none=True,
            ),
        )


class MemoryEntryRead(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(default="rev", min_length=1, max_length=160)
    visible_to_workflow: bool = False
    kind: str = Field(default="memory", min_length=1, max_length=80)
    summary: str = Field(default="Memory entry", min_length=1)
    content: str = Field(default="Memory entry", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    scope: MemoryScope = Field(default_factory=_default_memory_scope)
    provenance: MemoryProvenance
    revision: MemoryRevisionRead = Field(default_factory=_default_memory_revision)
    created_at: datetime
    updated_at: datetime | None = None
    outcome: MemoryOutcome | None = None
    reflections: list[MemoryReflection] = Field(default_factory=list)
    audit_links: MemoryAuditLinks | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_neutral_entry(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        memory_id = str(payload.get("memory_id") or payload.get("memoryId") or "memory")
        if "revision_id" not in payload and "revisionId" not in payload:
            payload["revision_id"] = f"{memory_id}:rev"
        if "kind" not in payload:
            payload["kind"] = "memory"
        if "summary" not in payload:
            payload["summary"] = "Memory entry"
        if "content" not in payload:
            payload["content"] = payload["summary"]
        if "scope" not in payload:
            payload["scope"] = {
                "scopeType": "run",
                "scopeKey": str(payload.get("memory_id") or memory_id),
            }
        if "revision" not in payload:
            payload["revision"] = {
                "revisionId": payload["revision_id"],
                "version": 1,
                "contentHash": _content_hash(str(payload["content"])),
                "createdAt": payload.get("created_at")
                or payload.get("createdAt")
                or datetime.now(UTC),
            }
        return payload

    @field_validator("memory_id", "revision_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory id field", max_length=160)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory entry field")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)

    @model_validator(mode="after")
    def validate_revision_identity(self) -> Self:
        if self.revision.revision_id != self.revision_id:
            raise ValueError("revision.revisionId must match revisionId")
        return self


class MemoryWriteRequest(CamelModel):
    kind: str = Field(default="memory", min_length=1, max_length=80)
    summary: str = Field(default="Memory entry", min_length=1)
    content: str = Field(default="Memory entry", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    scope: MemoryScope
    provenance: MemoryProvenance
    revision: MemoryRevisionPolicy = Field(default_factory=MemoryRevisionPolicy)
    idempotency_key: str | None = Field(default=None, max_length=160)
    idempotency_fallback_fields: tuple[str, ...] = Field(
        default=MEMORY_IDEMPOTENCY_FALLBACK_FIELDS,
    )

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory write request field")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="idempotencyKey", max_length=160)

    @field_validator("idempotency_fallback_fields", mode="before")
    @classmethod
    def validate_idempotency_fallback_fields(cls, value: object) -> tuple[str, ...]:
        return _normalize_idempotency_fallback_fields(value)

    def content_hash(self) -> str:
        return _content_hash(self.content)

    def idempotency_fallback_identity(self) -> dict[str, object]:
        return {
            "scope_type": self.scope.scope_type.value,
            "scope_key": self.scope.scope_key,
            "kind": self.kind,
            "content_hash": self.content_hash(),
            "source_run_id": self.provenance.run_id,
            "source_agent_key": self.provenance.agent_key,
            "source_step_id": self.provenance.step_id,
            "source_slot": self.provenance.slot,
        }


class MemoryWriteResult(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(default="rev", min_length=1, max_length=160)
    visible_to_workflow: bool = False
    revision_action: MemoryRevisionAction = MemoryRevisionAction.CREATED
    created_at: datetime
    provenance: MemoryProvenance
    revision: MemoryRevisionRead = Field(default_factory=_default_memory_revision)
    idempotency_key: str | None = Field(default=None, max_length=160)
    idempotency_fallback_fields: tuple[str, ...] = Field(
        default=MEMORY_IDEMPOTENCY_FALLBACK_FIELDS,
    )
    warnings: list[dict[str, object]] = Field(default_factory=list)
    audit_links: MemoryAuditLinks | None = None
    action: Literal["created", "existing"] = "created"

    @model_validator(mode="before")
    @classmethod
    def populate_neutral_result(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        memory_id = str(payload.get("memory_id") or payload.get("memoryId") or "memory")
        action = str(payload.get("action") or "created")
        if "revision_id" not in payload and "revisionId" not in payload:
            payload["revision_id"] = f"{memory_id}:rev"
        if "revision_action" not in payload and "revisionAction" not in payload:
            payload["revision_action"] = "reused" if action == "existing" else "created"
        if "revision" not in payload:
            payload["revision"] = {
                "revisionId": payload["revision_id"],
                "version": 1,
                "contentHash": _content_hash(memory_id),
                "createdAt": payload.get("created_at")
                or payload.get("createdAt")
                or datetime.now(UTC),
            }
        return payload

    @field_validator("memory_id", "revision_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory write result id", max_length=160)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="idempotencyKey", max_length=160)

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @field_validator("idempotency_fallback_fields", mode="before")
    @classmethod
    def validate_idempotency_fallback_fields(cls, value: object) -> tuple[str, ...]:
        return _normalize_idempotency_fallback_fields(value)

    @model_validator(mode="after")
    def validate_revision_identity(self) -> Self:
        if self.revision.revision_id != self.revision_id:
            raise ValueError("revision.revisionId must match revisionId")
        return self


class MemoryQuery(CamelModel):
    query: str | None = Field(default=None, max_length=1_000)
    scope: MemoryScope | None = None
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    kind: str | None = Field(default=None, max_length=80)
    agent_key: str | None = Field(default=None, max_length=120)
    workflow_key: str | None = Field(default=None, max_length=120)
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=MEMORY_LOOKUP_DEFAULT_LIMIT, ge=1, le=MEMORY_LOOKUP_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    max_characters: int = Field(
        default=MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS,
        ge=1,
        le=MEMORY_LOOKUP_MAX_CHARACTERS,
    )
    scope_mode: Literal["explicit-selectors", "current-context-fallback"] = (
        "current-context-fallback"
    )
    fallback_scope: Literal["current-run-package-agent"] = MEMORY_LOOKUP_CURRENT_CONTEXT_FALLBACK

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="query", max_length=1_000)

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: object) -> str | None:
        return _normalize_optional_kind(value)

    @field_validator("agent_key", "workflow_key", mode="before")
    @classmethod
    def normalize_context_filters(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Memory query field", max_length=120)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @model_validator(mode="after")
    def set_scope_mode(self) -> Self:
        has_explicit_selector = (
            self.scope is not None or bool(self.subject_refs) or self.kind is not None
        )
        self.scope_mode = (
            "explicit-selectors" if has_explicit_selector else "current-context-fallback"
        )
        return self


class MemoryRetrievalScore(CamelModel):
    retrieval_mode: Literal["lexical"] = "lexical"
    rank: int = Field(ge=1)
    score: float = 0.0
    scope_specificity: int = Field(default=0, ge=0)
    lexical_rank: int | None = Field(default=None, ge=1)
    lexical_score: float | None = None
    sources: list[Literal["lexical"]] = Field(default_factory=list)

    @field_validator("sources", mode="before")
    @classmethod
    def coerce_sources(cls, value: object) -> object:
        if value is None:
            return []
        return value


class MemoryPromptSnippet(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(default="rev", min_length=1, max_length=160)
    kind: str = Field(default="memory", min_length=1, max_length=80)
    summary: str = Field(default="Memory snippet", min_length=1)
    content: str = Field(default="Memory snippet", min_length=1)
    text: str = Field(default="", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    scope: MemoryScope = Field(default_factory=_default_memory_scope)
    provenance: MemoryProvenance
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    outcome: MemoryOutcome = Field(default_factory=_default_memory_outcome)
    reflections: list[MemoryReflection] = Field(default_factory=list)
    retrieval_score: MemoryRetrievalScore | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_neutral_snippet(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        memory_id = str(payload.get("memory_id") or payload.get("memoryId") or "memory")
        text = payload.get("text")
        if "revision_id" not in payload and "revisionId" not in payload:
            payload["revision_id"] = f"{memory_id}:rev"
        if "kind" not in payload:
            payload["kind"] = "memory"
        if "summary" not in payload:
            payload["summary"] = "Memory snippet"
        if "content" not in payload:
            payload["content"] = text or payload["summary"]
        if "text" not in payload:
            payload["text"] = payload["content"]
        if "scope" not in payload:
            payload["scope"] = {"scopeType": "run", "scopeKey": memory_id}
        if "created_at" not in payload and "createdAt" not in payload:
            payload["created_at"] = datetime.now(UTC)
        return payload

    @field_validator("memory_id", "revision_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Prompt snippet id", max_length=160)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Prompt snippet text")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryArtifactRead(_MemoryProjectionMixin):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(default="rev", min_length=1, max_length=160)
    visible_to_workflow: bool = False
    kind: str = Field(default="memory", min_length=1, max_length=80)
    summary: str = Field(default="Memory artifact", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    scope: MemoryScope = Field(default_factory=_default_memory_scope)
    provenance: MemoryProvenance
    created_at: datetime
    audit_links: MemoryAuditLinks | None = None
    source_graph_metadata: dict[str, object] | None = None

    @model_serializer(mode="wrap")
    def serialize_artifact_projection(
        self,
        handler: SerializerFunctionWrapHandler,
    ) -> dict[str, object]:
        payload = cast(dict[str, object], handler(self))
        for key in ("revisionId", "revision_id", "kind", "subjectRefs", "subject_refs", "scope"):
            _ = payload.pop(key, None)
        if payload.get("auditLinks") is None:
            _ = payload.pop("auditLinks", None)
        if payload.get("sourceGraphMetadata") is None:
            _ = payload.pop("sourceGraphMetadata", None)
        return payload

    @model_validator(mode="before")
    @classmethod
    def populate_neutral_artifact(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        memory_id = str(payload.get("memory_id") or payload.get("memoryId") or "memory")
        if "revision_id" not in payload and "revisionId" not in payload:
            payload["revision_id"] = f"{memory_id}:rev"
        if "kind" not in payload:
            payload["kind"] = "memory"
        if "scope" not in payload:
            payload["scope"] = {"scopeType": "run", "scopeKey": memory_id}
        return payload

    @field_validator("memory_id", "revision_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory artifact id", max_length=160)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value)

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory artifact summary")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryApiAccessContext(CamelModel):
    run_id: int | None = Field(default=None, ge=1)
    package_key: str = Field(min_length=1, max_length=120)
    workflow_key: str | None = Field(default=None, max_length=120)
    agent_key: str | None = Field(default=None, max_length=120)

    @field_validator("package_key", mode="before")
    @classmethod
    def validate_package_key(cls, value: object) -> str:
        return _normalize_namespace_key(value, field_name="accessContext.packageKey")

    @field_validator("workflow_key", "agent_key", mode="before")
    @classmethod
    def validate_optional_context_key(cls, value: object) -> str | None:
        normalized = _normalize_optional_text(
            value,
            field_name="accessContext ref",
            max_length=120,
        )
        if normalized is None:
            return None
        return _normalize_namespace_key(normalized, field_name="accessContext ref")


class MemoryApiAccessRequest(CamelModel):
    access_context: MemoryApiAccessContext


class MemoryApiListRequest(MemoryApiAccessRequest):
    visibility: Literal["explicit-scope"] = "explicit-scope"
    scope: MemoryScope
    query: str | None = Field(default=None, max_length=1_000)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    kind: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=MEMORY_LOOKUP_DEFAULT_LIMIT, ge=1, le=MEMORY_LOOKUP_MAX_LIMIT)
    offset: int = Field(default=0, ge=0)
    max_characters: int = Field(
        default=MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS,
        ge=1,
        le=MEMORY_LOOKUP_MAX_CHARACTERS,
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="query", max_length=1_000)

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: object) -> str | None:
        return _normalize_optional_kind(value)

    @field_validator("subject_refs", "tags", mode="before")
    @classmethod
    def coerce_lists(cls, value: object) -> object:
        return [] if value is None else value

    def to_query(self) -> MemoryQuery:
        return MemoryQuery(
            query=self.query,
            scope=self.scope,
            subject_refs=self.subject_refs,
            kind=self.kind,
            tags=self.tags,
            limit=self.limit,
            offset=self.offset,
            max_characters=self.max_characters,
        )


class MemoryApiResolveRequest(MemoryApiAccessRequest):
    outcome: MemoryOutcome


class MemoryApiReflectRequest(MemoryApiAccessRequest):
    reflection: MemoryReflection


class MemoryApiListItemRead(CamelModel):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    scope: MemoryScope
    provenance: MemoryProvenance
    created_at: datetime
    retrieval_score: MemoryRetrievalScore | None = None

    @classmethod
    def from_snippet(cls, snippet: MemoryPromptSnippet) -> Self:
        return cls(
            memory_id=snippet.memory_id,
            revision_id=snippet.revision_id,
            kind=snippet.kind,
            summary=snippet.summary,
            content=snippet.content,
            subject_refs=snippet.subject_refs,
            scope=snippet.scope,
            provenance=snippet.provenance,
            created_at=snippet.created_at,
            retrieval_score=snippet.retrieval_score,
        )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryApiEntryRead(CamelModel):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    visible_to_workflow: bool
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    scope: MemoryScope
    provenance: MemoryProvenance
    revision: MemoryRevisionRead
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_entry(cls, entry: MemoryEntryRead) -> Self:
        return cls.model_validate(entry.dump_for_projection("api-visible"))

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class MemoryApiListRead(CamelModel):
    items: list[MemoryApiListItemRead]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_LOOKUP_MAX_LIMIT)
    offset: int = Field(ge=0)
    visibility: Literal["explicit-scope"]
    scope: MemoryScope


class MemoryApiRevisionRead(CamelModel):
    revision_id: str = Field(min_length=1, max_length=160)
    version: int = Field(ge=1)
    visible_to_workflow: bool
    revision_action: MemoryRevisionAction
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    supersedes_revision_id: str | None = Field(default=None, max_length=160)
    source_run_id: int = Field(ge=1)
    source_agent_key: str = Field(min_length=1, max_length=120)
    source_step_id: str | None = Field(default=None, max_length=120)
    source_slot: str | None = Field(default=None, max_length=120)
    trace_span_id: str | None = Field(default=None, max_length=255)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryApiRevisionListRead(CamelModel):
    items: list[MemoryApiRevisionRead]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_API_MAX_REVISIONS)
    offset: int = Field(ge=0)


class MemoryApiEventRead(CamelModel):
    event_id: int = Field(ge=1)
    run_id: int = Field(ge=1)
    event_type: str = Field(min_length=1, max_length=40)
    memory_id: str | None = Field(default=None, max_length=160)
    revision_id: str | None = Field(default=None, max_length=160)
    retrieval_mode: str | None = Field(default=None, max_length=40)
    filters: dict[str, object] = Field(default_factory=dict)
    budget: dict[str, object] = Field(default_factory=dict)
    excerpt: str | None = None
    injected_text: str | None = None
    result_snapshot: dict[str, object] = Field(default_factory=dict)
    status_snapshot: dict[str, object] = Field(default_factory=dict)
    step_id: str | None = Field(default=None, max_length=120)
    invocation_id: str | None = Field(default=None, max_length=160)
    trace_span_id: str | None = Field(default=None, max_length=255)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)


class MemoryApiEventListRead(CamelModel):
    items: list[MemoryApiEventRead]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_API_MAX_EVENTS)
    offset: int = Field(ge=0)


MEMORY_ADMIN_LIST_DEFAULT_LIMIT: Final = 50
MEMORY_ADMIN_LIST_MAX_LIMIT: Final = 200
MemoryAdminSort = Literal["updatedAtDesc", "createdAtDesc"]


class MemoryAdminListQuery(CamelModel):
    package_key: str | None = Field(default=None, max_length=120)
    workflow_key: str | None = Field(default=None, max_length=120)
    agent_key: str | None = Field(default=None, max_length=120)
    run_id: int | None = Field(default=None, ge=1)
    scope_type: MemoryScopeType | None = None
    kind: str | None = Field(default=None, max_length=80)
    visible_to_workflow: bool | None = None
    query: str | None = Field(default=None, max_length=1_000)
    limit: int = Field(
        default=MEMORY_ADMIN_LIST_DEFAULT_LIMIT,
        ge=1,
        le=MEMORY_ADMIN_LIST_MAX_LIMIT,
    )
    offset: int = Field(default=0, ge=0)
    sort: MemoryAdminSort = "updatedAtDesc"

    @field_validator("package_key", "workflow_key", "agent_key", mode="before")
    @classmethod
    def normalize_context_key(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="Memory admin filter", max_length=120)

    @field_validator("kind", mode="before")
    @classmethod
    def normalize_kind(cls, value: object) -> str | None:
        return _normalize_optional_kind(value)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="query", max_length=1_000)


class MemoryAdminListItemRead(CamelModel):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    visible_to_workflow: bool
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    excerpt: str = Field(default="", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    scope: MemoryScope
    provenance: MemoryProvenance
    created_at: datetime
    updated_at: datetime | None = None
    last_event_type: str | None = Field(default=None, max_length=40)

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class MemoryAdminListRead(CamelModel):
    items: list[MemoryAdminListItemRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_ADMIN_LIST_MAX_LIMIT)
    offset: int = Field(ge=0)
    sort: MemoryAdminSort = "updatedAtDesc"


class MemoryAdminEntryRead(CamelModel):
    memory_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    visible_to_workflow: bool
    kind: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    scope: MemoryScope
    provenance: MemoryProvenance
    revision: MemoryRevisionRead
    created_at: datetime
    updated_at: datetime | None = None
    outcome: MemoryOutcome | None = None
    reflections: list[MemoryReflection] = Field(default_factory=list)
    audit_links: MemoryAuditLinks | None = None

    @classmethod
    def from_entry(cls, entry: MemoryEntryRead) -> Self:
        return cls.model_validate(
            entry.model_dump(mode="json", by_alias=True, exclude_none=True),
        )

    @field_validator("created_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return ensure_timezone(value)


class MemoryAdminCreateRequest(CamelModel):
    kind: str = Field(default="memory", min_length=1, max_length=80)
    summary: str = Field(default="Memory entry", min_length=1)
    content: str = Field(default="Memory entry", min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    scope: MemoryScope
    provenance: MemoryProvenance
    visible_to_workflow: bool = True
    idempotency_key: str | None = Field(default=None, max_length=160)

    @field_validator("kind", mode="before")
    @classmethod
    def validate_kind(cls, value: object) -> str:
        return _normalize_kind(value)

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory admin create field")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: object) -> str | None:
        return _normalize_optional_text(value, field_name="idempotencyKey", max_length=160)

    def to_write_request(self) -> MemoryWriteRequest:
        return MemoryWriteRequest(
            kind=self.kind,
            summary=self.summary,
            content=self.content,
            subject_refs=self.subject_refs,
            attributes=self.attributes,
            scope=self.scope,
            provenance=self.provenance,
            idempotency_key=self.idempotency_key,
        )

    def to_outcome(self) -> MemoryOutcome:
        return MemoryOutcome(summary=self.summary)


class MemoryAdminRevisionCreateRequest(CamelModel):
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    subject_refs: list[MemorySubjectRef] = Field(default_factory=list)
    attributes: MemoryAttributes = Field(default_factory=dict)
    provenance: MemoryProvenance

    @field_validator("summary", "content", mode="before")
    @classmethod
    def validate_text(cls, value: object) -> str:
        return _normalize_required_text(value, field_name="Memory admin revision field")

    @field_validator("subject_refs", mode="before")
    @classmethod
    def coerce_subject_refs(cls, value: object) -> object:
        return [] if value is None else value

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)


class MemoryAdminWorkflowVisibilityUpdateRequest(CamelModel):
    visible_to_workflow: bool
    summary: str = Field(default="Memory workflow visibility updated", min_length=1)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    attributes: MemoryAttributes = Field(default_factory=dict)

    @field_validator("summary", mode="before")
    @classmethod
    def validate_summary(cls, value: object) -> str:
        return _normalize_required_text(
            value,
            field_name="Memory admin workflow visibility summary",
        )

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return ensure_timezone(value)

    @field_validator("attributes", mode="before")
    @classmethod
    def normalize_attributes(cls, value: object) -> MemoryAttributes:
        return _normalize_attributes(value)

    def to_outcome(self) -> MemoryOutcome:
        return MemoryOutcome(
            summary=self.summary,
            observed_at=self.observed_at,
            attributes=self.attributes,
        )


class MemoryAdminRevisionListRead(CamelModel):
    items: list[MemoryApiRevisionRead]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_API_MAX_REVISIONS)
    offset: int = Field(ge=0)


class MemoryAdminEventListRead(CamelModel):
    items: list[MemoryApiEventRead]
    count: int = Field(ge=0)
    limit: int = Field(ge=1, le=MEMORY_API_MAX_EVENTS)
    offset: int = Field(ge=0)


__all__ = [
    "INVALID_MEMORY_ID_CODE",
    "MEMORY_API_MAX_EVENTS",
    "MEMORY_ADMIN_LIST_DEFAULT_LIMIT",
    "MEMORY_ADMIN_LIST_MAX_LIMIT",
    "MEMORY_API_MAX_REVISIONS",
    "MEMORY_CORE_RUNTIME_TOOL_KEYS",
    "MEMORY_DEFERRED_GET_DECISION",
    "MEMORY_DUPLICATE_REVISION_BEHAVIOR",
    "MEMORY_IDEMPOTENCY_FALLBACK_FIELDS",
    "MEMORY_LOOKUP_CURRENT_CONTEXT_FALLBACK",
    "MEMORY_LOOKUP_DEFAULT_LIMIT",
    "MEMORY_LOOKUP_DEFAULT_MAX_CHARACTERS",
    "MEMORY_LOOKUP_MAX_CHARACTERS",
    "MEMORY_LOOKUP_MAX_LIMIT",
    "MEMORY_MODEL_VISIBLE_EXCLUDED_FIELDS",
    "MEMORY_NAMESPACE_ACCESS_DENIED_CODE",
    "MEMORY_NAMESPACE_ACCESS_DENIED_MESSAGE",
    "MEMORY_NAMESPACE_SCOPE_SEPARATOR",
    "MEMORY_NOT_FOUND_CODE",
    "MEMORY_PROJECTION_MATRIX",
    "MEMORY_REVISION_WRITE_MODE",
    "MemoryAdminCreateRequest",
    "MemoryAdminEntryRead",
    "MemoryAdminEventListRead",
    "MemoryAdminListItemRead",
    "MemoryAdminListQuery",
    "MemoryAdminListRead",
    "MemoryAdminRevisionCreateRequest",
    "MemoryAdminRevisionListRead",
    "MemoryAdminSort",
    "MemoryAdminWorkflowVisibilityUpdateRequest",
    "MemoryApiAccessContext",
    "MemoryApiAccessRequest",
    "MemoryApiEntryRead",
    "MemoryApiEventListRead",
    "MemoryApiEventRead",
    "MemoryApiListItemRead",
    "MemoryApiListRead",
    "MemoryApiListRequest",
    "MemoryApiReflectRequest",
    "MemoryApiResolveRequest",
    "MemoryApiRevisionListRead",
    "MemoryApiRevisionRead",
    "MemoryArtifactRead",
    "MemoryAuditLinks",
    "MemoryAuditReportLink",
    "MemoryAttributes",
    "MemoryContent",
    "MemoryEntryRead",
    "MemoryId",
    "MemoryNamespaceAction",
    "MemoryNamespaceGrant",
    "MemoryNamespaceGrantSubject",
    "MemoryNamespaceSelector",
    "MemoryOutcome",
    "MemoryProjection",
    "MemoryPromptSnippet",
    "MemoryProvenance",
    "MemoryRetrievalScore",
    "MemoryQuery",
    "MemoryReflection",
    "MemoryRevisionAction",
    "MemoryRevisionPolicy",
    "MemoryRevisionRead",
    "MemoryScope",
    "MemoryScopeType",
    "MemorySubjectRef",
    "MemoryWriteRequest",
    "MemoryWriteResult",
    "invalid_memory_id_error",
    "memory_not_found_error",
]
