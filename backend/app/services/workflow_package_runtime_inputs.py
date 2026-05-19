# pyright: reportExplicitAny=false
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from app.core.errors import validation_error

RUNTIME_INPUT_PAYLOAD_MAX_BYTES = 128 * 1024
RUNTIME_INPUT_PAYLOAD_MAX_DEPTH = 12
RUNTIME_INPUT_PAYLOAD_MAX_NODES = 4096
RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS = 2048

_RUNTIME_INPUT_PAYLOAD_VALIDATION_MESSAGE = "Runtime input payload validation failed"


@dataclass(frozen=True)
class RuntimeInputWorkflowMetadata:
    workflow_key: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class RuntimeInputStoredMetadata:
    workflow_key: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str


@dataclass(frozen=True)
class RuntimeInputStaleEvaluation:
    stale: bool
    reasons: list[dict[str, str | None]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "stale": self.stale,
            "reasons": [dict(reason) for reason in self.reasons],
        }


@dataclass
class _PayloadStats:
    nodes: int = 0
    object_keys: int = 0


def validate_runtime_input_payload_safety(
    payload: object,
    *,
    field: str = "payload",
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        _raise_payload_validation(field, "Payload must be a JSON object")

    payload_map = cast(dict[str, Any], payload)
    _collect_payload_stats(payload_map, field=field)
    try:
        serialized = _canonical_json(payload_map)
    except (TypeError, ValueError, RecursionError):
        _raise_payload_validation(field, "Payload must be JSON serializable")

    actual_bytes = len(serialized.encode("utf-8"))
    if actual_bytes > RUNTIME_INPUT_PAYLOAD_MAX_BYTES:
        _raise_payload_validation(
            field,
            f"Payload must serialize to at most {RUNTIME_INPUT_PAYLOAD_MAX_BYTES} bytes",
            limit=RUNTIME_INPUT_PAYLOAD_MAX_BYTES,
            actual=actual_bytes,
        )
    return payload_map


def runtime_input_schema_fingerprint(input_schema: object) -> str:
    serialized = _canonical_json(input_schema)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def build_runtime_input_current_metadata(
    *,
    workflow_key: str,
    manifest_hash: str,
    compiled_hash: str,
    compiled_plan: Mapping[str, Any],
) -> RuntimeInputWorkflowMetadata | None:
    workflow = _select_workflow(compiled_plan, workflow_key)
    if workflow is None:
        return None
    raw_input_schema = workflow.get("inputSchema")
    input_schema = (
        cast(dict[str, Any], raw_input_schema) if isinstance(raw_input_schema, dict) else {}
    )
    schema_snapshot: dict[str, Any] = deepcopy(input_schema)
    return RuntimeInputWorkflowMetadata(
        workflow_key=str(workflow.get("key") or workflow_key),
        manifest_hash=manifest_hash,
        compiled_hash=compiled_hash,
        schema_fingerprint=runtime_input_schema_fingerprint(schema_snapshot),
        input_schema=schema_snapshot,
    )


def evaluate_runtime_input_staleness(
    stored_metadata: RuntimeInputStoredMetadata,
    current_metadata: RuntimeInputWorkflowMetadata | None,
) -> RuntimeInputStaleEvaluation:
    if current_metadata is None:
        return RuntimeInputStaleEvaluation(
            stale=True,
            reasons=[
                {
                    "field": "workflowKey",
                    "issue": "Saved workflow is no longer present in the current package",
                    "stored": stored_metadata.workflow_key,
                    "current": None,
                }
            ],
        )

    reasons: list[dict[str, str | None]] = []
    _append_stale_reason(
        reasons,
        field="workflowKey",
        stored=stored_metadata.workflow_key,
        current=current_metadata.workflow_key,
        issue="Saved workflow key differs from current metadata",
    )
    _append_stale_reason(
        reasons,
        field="manifestHash",
        stored=stored_metadata.manifest_hash,
        current=current_metadata.manifest_hash,
        issue="Saved manifest hash differs from the current package",
    )
    _append_stale_reason(
        reasons,
        field="compiledHash",
        stored=stored_metadata.compiled_hash,
        current=current_metadata.compiled_hash,
        issue="Saved compiled hash differs from the current package",
    )
    _append_stale_reason(
        reasons,
        field="schemaFingerprint",
        stored=stored_metadata.schema_fingerprint,
        current=current_metadata.schema_fingerprint,
        issue="Saved input schema fingerprint differs from the current workflow",
    )
    return RuntimeInputStaleEvaluation(stale=bool(reasons), reasons=reasons)


def _collect_payload_stats(payload: dict[str, Any], *, field: str) -> None:
    stats = _PayloadStats()
    _walk_payload(payload, depth=1, path=field, active=set(), stats=stats)


def _walk_payload(
    value: object,
    *,
    depth: int,
    path: str,
    active: set[int],
    stats: _PayloadStats,
) -> None:
    stats.nodes += 1
    if stats.nodes > RUNTIME_INPUT_PAYLOAD_MAX_NODES:
        _raise_payload_validation(
            path,
            f"Payload may contain at most {RUNTIME_INPUT_PAYLOAD_MAX_NODES} JSON nodes",
            limit=RUNTIME_INPUT_PAYLOAD_MAX_NODES,
            actual=stats.nodes,
        )
    if depth > RUNTIME_INPUT_PAYLOAD_MAX_DEPTH:
        _raise_payload_validation(
            path,
            f"Payload nesting depth must be at most {RUNTIME_INPUT_PAYLOAD_MAX_DEPTH}",
            limit=RUNTIME_INPUT_PAYLOAD_MAX_DEPTH,
            actual=depth,
        )

    if isinstance(value, dict):
        _walk_mapping(
            cast(dict[object, object], value),
            depth=depth,
            path=path,
            active=active,
            stats=stats,
        )
        return
    if isinstance(value, list):
        _walk_sequence(
            cast(list[object], value),
            depth=depth,
            path=path,
            active=active,
            stats=stats,
        )
        return
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        _raise_payload_validation(path, "Payload numbers must be finite")
    _raise_payload_validation(path, "Payload values must be JSON-compatible")


def _walk_mapping(
    value: dict[object, object],
    *,
    depth: int,
    path: str,
    active: set[int],
    stats: _PayloadStats,
) -> None:
    container_id = id(value)
    if container_id in active:
        _raise_payload_validation(path, "Payload must not contain circular references")
    active.add(container_id)
    try:
        stats.object_keys += len(value)
        if stats.object_keys > RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS:
            _raise_payload_validation(
                path,
                (
                    "Payload objects may contain at most "
                    f"{RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS} keys"
                ),
                limit=RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS,
                actual=stats.object_keys,
            )
        for raw_key, child in value.items():
            if not isinstance(raw_key, str):
                _raise_payload_validation(path, "Payload object keys must be strings")
            _walk_payload(
                child,
                depth=depth + 1,
                path=_join_payload_path(path, raw_key),
                active=active,
                stats=stats,
            )
    finally:
        active.remove(container_id)


def _walk_sequence(
    value: list[object],
    *,
    depth: int,
    path: str,
    active: set[int],
    stats: _PayloadStats,
) -> None:
    container_id = id(value)
    if container_id in active:
        _raise_payload_validation(path, "Payload must not contain circular references")
    active.add(container_id)
    try:
        for index, child in enumerate(value):
            _walk_payload(
                child,
                depth=depth + 1,
                path=f"{path}[{index}]",
                active=active,
                stats=stats,
            )
    finally:
        active.remove(container_id)


def _select_workflow(
    compiled_plan: Mapping[str, Any],
    workflow_key: str,
) -> Mapping[str, Any] | None:
    raw_workflows = compiled_plan.get("workflows")
    if not isinstance(raw_workflows, list):
        return None
    workflows = cast(list[object], raw_workflows)
    for raw_workflow in workflows:
        if not isinstance(raw_workflow, Mapping):
            continue
        workflow = cast(Mapping[str, Any], raw_workflow)
        if str(workflow.get("key") or "") == workflow_key:
            return workflow
    return None


def _append_stale_reason(
    reasons: list[dict[str, str | None]],
    *,
    field: str,
    stored: str,
    current: str,
    issue: str,
) -> None:
    if stored == current:
        return
    reasons.append(
        {
            "field": field,
            "issue": issue,
            "stored": stored,
            "current": current,
        }
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _join_payload_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{key!r}]"


def _raise_payload_validation(
    field: str,
    issue: str,
    **extra: int,
) -> NoReturn:
    detail: dict[str, Any] = {"field": field, "issue": issue}
    detail.update(extra)
    raise validation_error(_RUNTIME_INPUT_PAYLOAD_VALIDATION_MESSAGE, [detail])


__all__ = [
    "RUNTIME_INPUT_PAYLOAD_MAX_BYTES",
    "RUNTIME_INPUT_PAYLOAD_MAX_DEPTH",
    "RUNTIME_INPUT_PAYLOAD_MAX_NODES",
    "RUNTIME_INPUT_PAYLOAD_MAX_OBJECT_KEYS",
    "RuntimeInputStaleEvaluation",
    "RuntimeInputStoredMetadata",
    "RuntimeInputWorkflowMetadata",
    "build_runtime_input_current_metadata",
    "evaluate_runtime_input_staleness",
    "runtime_input_schema_fingerprint",
    "validate_runtime_input_payload_safety",
]
