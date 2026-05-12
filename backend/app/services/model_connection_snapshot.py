from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from app.models.model_connection import ModelConnection

MODEL_CONNECTION_RUNTIME_SNAPSHOT_KEYS = (
    "base_url",
    "model_id",
    "reasoning_effort",
    "connection_kind",
    "api_style",
    "timeout_seconds",
)


@dataclass(frozen=True)
class ModelConnectionRuntimeSnapshot:
    base_url: str
    model_id: str
    reasoning_effort: str | None
    connection_kind: str | None
    api_style: str
    timeout_seconds: int


def build_model_connection_runtime_snapshot(
    connection: ModelConnection,
) -> dict[str, object]:
    return {
        "base_url": connection.base_url,
        "model_id": connection.model_id,
        "reasoning_effort": connection.reasoning_effort,
        "connection_kind": connection.connection_kind,
        "api_style": connection.api_style,
        "timeout_seconds": connection.timeout_seconds,
    }


def parse_model_connection_runtime_snapshot(
    raw_snapshot: object,
) -> ModelConnectionRuntimeSnapshot:
    if not isinstance(raw_snapshot, Mapping):
        raise ValueError("Model connection snapshot must be an object")
    snapshot = _snapshot_mapping(cast(Mapping[object, object], raw_snapshot))
    missing_keys = [
        key
        for key in MODEL_CONNECTION_RUNTIME_SNAPSHOT_KEYS
        if (
            key not in {"api_style", "reasoning_effort", "connection_kind"}
            and key not in snapshot
        )
    ]
    if missing_keys:
        raise ValueError(
            "Model connection snapshot is missing required fields: " + ", ".join(missing_keys)
        )

    base_url = _required_snapshot_text(snapshot["base_url"], field_name="base_url")
    model_id = _required_snapshot_text(snapshot["model_id"], field_name="model_id")
    if "reasoning_effort" in snapshot:
        reasoning_effort = _snapshot_reasoning_effort(snapshot["reasoning_effort"])
    else:
        reasoning_effort = "medium"
    if "connection_kind" in snapshot:
        connection_kind = _snapshot_connection_kind(snapshot["connection_kind"])
    else:
        connection_kind = None
    api_style = _required_snapshot_text(
        snapshot.get("api_style", "responses"),
        field_name="api_style",
    )
    if api_style not in {"responses", "chat_completions"}:
        raise ValueError("Model connection snapshot api_style is invalid")
    timeout_seconds = snapshot["timeout_seconds"]
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
        raise ValueError("Model connection snapshot timeout_seconds must be an integer")
    if timeout_seconds <= 0:
        raise ValueError("Model connection snapshot timeout_seconds must be positive")

    return ModelConnectionRuntimeSnapshot(
        base_url=base_url,
        model_id=model_id,
        reasoning_effort=reasoning_effort,
        connection_kind=connection_kind,
        api_style=api_style,
        timeout_seconds=timeout_seconds,
    )


def snapshot_to_json(
    snapshot: ModelConnectionRuntimeSnapshot,
) -> dict[str, object]:
    return {
        "base_url": snapshot.base_url,
        "model_id": snapshot.model_id,
        "reasoning_effort": snapshot.reasoning_effort,
        "connection_kind": snapshot.connection_kind,
        "api_style": snapshot.api_style,
        "timeout_seconds": snapshot.timeout_seconds,
    }


def _snapshot_mapping(raw_snapshot: Mapping[object, object]) -> Mapping[str, object]:
    if not all(isinstance(key, str) for key in raw_snapshot):
        raise ValueError("Model connection snapshot keys must be strings")
    return cast(Mapping[str, object], raw_snapshot)


def _required_snapshot_text(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model connection snapshot {field_name} must be a non-empty string")
    return value.strip()


def _snapshot_reasoning_effort(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Model connection snapshot reasoning_effort must be a string or null")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Model connection snapshot reasoning_effort must be a non-empty string")
    if len(normalized) > 128:
        raise ValueError(
            "Model connection snapshot reasoning_effort must be at most 128 characters"
        )
    return normalized


def _snapshot_connection_kind(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Model connection snapshot connection_kind must be a string or null")
    normalized = value.strip()
    if not normalized:
        raise ValueError("Model connection snapshot connection_kind must be a non-empty string")
    if normalized not in {"provider", "deterministic_smoke"}:
        raise ValueError("Model connection snapshot connection_kind is invalid")
    return normalized


__all__ = [
    "MODEL_CONNECTION_RUNTIME_SNAPSHOT_KEYS",
    "ModelConnectionRuntimeSnapshot",
    "build_model_connection_runtime_snapshot",
    "parse_model_connection_runtime_snapshot",
    "snapshot_to_json",
]
