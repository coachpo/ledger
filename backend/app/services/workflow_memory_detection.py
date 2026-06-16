from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_OPENAI_STYLE_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_PASSWORD_RE = re.compile(r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_SECRET_KEY_NAMES = {"api_key", "apikey", "password", "passwd", "private_key", "token"}


def detect_workflow_memory_policy_hits(content: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    secret_hits: list[dict[str, str]] = []
    sensitive_hits: list[dict[str, str]] = []
    for path, value in _walk_json(content):
        normalized_path = path.lower().replace("-", "_")
        if any(part in _SECRET_KEY_NAMES for part in normalized_path.split(".")):
            secret_hits.append({"detector": "secret_field", "path": path})
        if not isinstance(value, str):
            continue
        if _OPENAI_STYLE_KEY_RE.search(value):
            secret_hits.append({"detector": "api_key", "path": path})
        if _PASSWORD_RE.search(value):
            secret_hits.append({"detector": "password", "path": path})
        if _PRIVATE_KEY_RE.search(value):
            secret_hits.append({"detector": "private_key", "path": path})
        if _EMAIL_RE.search(value):
            sensitive_hits.append({"detector": "email", "path": path})
        if _SSN_RE.search(value):
            sensitive_hits.append({"detector": "ssn", "path": path})
    return {"secrets": secret_hits, "sensitiveData": sensitive_hits}


def merge_detector_hits(
    existing: dict[str, Any] | None,
    detected: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    merged: dict[str, Any] = {key: value for key, value in (existing or {}).items()}
    for key, hits in detected.items():
        if not hits:
            merged.setdefault(key, [])
            continue
        previous = merged.get(key)
        previous_hits: list[object] = previous if isinstance(previous, list) else []
        merged[key] = [*previous_hits, *hits]
    return merged


def _walk_json(value: Any, *, prefix: str = "content") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}"
            yield from _walk_json(item, prefix=child_prefix)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_json(item, prefix=f"{prefix}[{index}]")
        return
    yield prefix, value


__all__ = ["detect_workflow_memory_policy_hits", "merge_detector_hits"]
