# pyright: reportExplicitAny=false
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.errors import ApiError, business_rule_error
from app.core.formatting import to_utc
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.run_input_validation import validate_run_input_payload
from app.services.workflow_package_runtime_inputs import validate_runtime_input_payload_safety

SCHEDULE_TEMPLATE_INVALID_EXPRESSION: Final = "schedule_template_invalid_expression"
SCHEDULE_TEMPLATE_MISSING_VALUE: Final = "schedule_template_missing_value"
SCHEDULE_RENDER_VALIDATION_FAILED: Final = "schedule_render_validation_failed"

_ALLOWED_NAMESPACES: Final = frozenset({"schedule", "fire", "window", "lastRun", "vars"})
_ALLOWED_CONTEXT_PLACEHOLDERS: Final = frozenset(
    {
        "schedule.id",
        "schedule.name",
        "schedule.timezone",
        "schedule.packageKey",
        "schedule.workflowKey",
        "fire.id",
        "fire.reason",
        "fire.scheduledFor",
        "fire.scheduledLocalDate",
        "fire.scheduledLocalTime",
        "fire.scheduledLocalDateTime",
        "fire.materializedAt",
        "window.start",
        "window.end",
        "window.startDate",
        "window.endDate",
        "lastRun.id",
        "lastRun.status",
        "lastRun.completedAt",
    }
)
_IDENTIFIER_RE: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PLACEHOLDER_RE: Final = re.compile(r"{{\s*([^{}]+?)\s*}}")
_EXACT_PLACEHOLDER_RE: Final = re.compile(r"^\s*{{\s*([^{}]+?)\s*}}\s*$")
_ESCAPED_LITERAL_RE: Final = re.compile(r"\\{{(.*?)}}")
_ESCAPED_OPEN: Final = "\ufff0"
_ESCAPED_CLOSE: Final = "\ufff1"


@dataclass(frozen=True)
class ScheduledInputLastRunContext:
    id: int | None = None
    status: str | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class ScheduledInputTemplateRenderResult:
    rendered_parameters: dict[str, Any]
    validation_errors: list[dict[str, Any]]

    @property
    def ready(self) -> bool:
        return not self.validation_errors


@dataclass(frozen=True)
class ScheduledInputRenderPreview:
    template_context: dict[str, Any]
    rendered_parameters: dict[str, Any]
    validation_errors: list[dict[str, Any]]
    validated_parameters: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return not self.validation_errors

    def parameters_for_launch(self) -> dict[str, Any]:
        if not self.ready:
            raise ValueError("Scheduled input render preview is not ready")
        source = self.validated_parameters or self.rendered_parameters
        return deepcopy(source)

    def to_payload(self) -> dict[str, Any]:
        return {
            "templateContext": deepcopy(self.template_context),
            "renderedParameters": deepcopy(self.rendered_parameters),
            "validationErrors": [dict(error) for error in self.validation_errors],
            "ready": self.ready,
        }


def build_scheduled_input_template_context(
    *,
    schedule_id: int | None,
    schedule_name: str,
    schedule_timezone: str,
    package_key: str,
    workflow_key: str,
    fire_id: int | None,
    fire_reason: str,
    scheduled_for: datetime,
    scheduled_local_date: str | None,
    scheduled_local_time: str | None,
    scheduled_local_datetime: str | None,
    materialized_at: datetime | None = None,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    last_run: ScheduledInputLastRunContext | None = None,
    template_vars: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_window_end = window_end or scheduled_for
    schedule_context: dict[str, Any] = {
        "name": schedule_name,
        "timezone": schedule_timezone,
        "packageKey": package_key,
        "workflowKey": workflow_key,
    }
    _set_if_not_none(schedule_context, "id", schedule_id)

    fire_context: dict[str, Any] = {
        "reason": fire_reason,
        "scheduledFor": _utc_isoformat(scheduled_for),
    }
    _set_if_not_none(fire_context, "id", fire_id)
    _set_if_not_none(fire_context, "scheduledLocalDate", scheduled_local_date)
    _set_if_not_none(fire_context, "scheduledLocalTime", scheduled_local_time)
    _set_if_not_none(fire_context, "scheduledLocalDateTime", scheduled_local_datetime)
    _set_if_not_none(fire_context, "materializedAt", _optional_utc_isoformat(materialized_at))

    window_context: dict[str, Any] = {"end": _utc_isoformat(resolved_window_end)}
    _set_if_not_none(
        window_context,
        "endDate",
        _local_date(resolved_window_end, schedule_timezone),
    )
    if window_start is not None:
        window_context["start"] = _utc_isoformat(window_start)
        _set_if_not_none(
            window_context,
            "startDate",
            _local_date(window_start, schedule_timezone),
        )

    context = {
        "schedule": schedule_context,
        "fire": fire_context,
        "window": window_context,
        "lastRun": _last_run_context(last_run),
        "vars": deepcopy(dict(template_vars or {})),
    }
    return context


def render_scheduled_input_template(
    input_template: object,
    template_context: Mapping[str, Any],
) -> ScheduledInputTemplateRenderResult:
    errors: list[dict[str, Any]] = []
    safe_template = _validate_payload_safety(input_template, field="inputTemplate", errors=errors)
    raw_vars = template_context.get("vars", {})
    _ = _validate_payload_safety(raw_vars, field="templateVars", errors=errors)
    if errors or safe_template is None:
        return ScheduledInputTemplateRenderResult(
            rendered_parameters={},
            validation_errors=errors,
        )

    rendered = _render_value(
        safe_template,
        path="inputTemplate",
        template_context=template_context,
        errors=errors,
    )
    if errors:
        return ScheduledInputTemplateRenderResult(
            rendered_parameters={},
            validation_errors=errors,
        )
    safe_rendered = _validate_payload_safety(
        rendered,
        field="renderedParameters",
        errors=errors,
    )
    return ScheduledInputTemplateRenderResult(
        rendered_parameters=deepcopy(safe_rendered or {}),
        validation_errors=errors,
    )


def render_and_validate_scheduled_input_template(
    *,
    input_template: object,
    template_context: Mapping[str, Any],
    input_schema: dict[str, Any],
    schema_compiler: OutputSchemaCompiler,
    candidate_key: str = "schedule_input",
    resource_name: str = "workflowPackage",
) -> ScheduledInputRenderPreview:
    render_result = render_scheduled_input_template(input_template, template_context)
    if not render_result.ready:
        return ScheduledInputRenderPreview(
            template_context=deepcopy(dict(template_context)),
            rendered_parameters={},
            validation_errors=render_result.validation_errors,
        )
    try:
        validated_parameters = validate_run_input_payload(
            schema_compiler=schema_compiler,
            input_schema=input_schema,
            input_payload=render_result.rendered_parameters,
            candidate_key=candidate_key,
            resource_name=resource_name,
        )
    except ApiError as exc:
        return ScheduledInputRenderPreview(
            template_context=deepcopy(dict(template_context)),
            rendered_parameters=deepcopy(render_result.rendered_parameters),
            validation_errors=_api_error_details(exc),
        )
    return ScheduledInputRenderPreview(
        template_context=deepcopy(dict(template_context)),
        rendered_parameters=deepcopy(validated_parameters),
        validation_errors=[],
        validated_parameters=validated_parameters,
    )


def require_scheduled_input_render_ready(preview: ScheduledInputRenderPreview) -> dict[str, Any]:
    if preview.ready:
        return preview.parameters_for_launch()
    code = _first_error_code(preview.validation_errors) or SCHEDULE_RENDER_VALIDATION_FAILED
    raise business_rule_error(
        code,
        "Scheduled input template validation failed",
        details=preview.validation_errors,
    )


def _render_value(
    value: object,
    *,
    path: str,
    template_context: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> Any:
    if isinstance(value, dict):
        return {
            key: _render_value(
                child,
                path=_join_path(path, key),
                template_context=template_context,
                errors=errors,
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            _render_value(
                child,
                path=f"{path}[{index}]",
                template_context=template_context,
                errors=errors,
            )
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        return _render_string(value, path=path, template_context=template_context, errors=errors)
    return deepcopy(value)


def _render_string(
    value: str,
    *,
    path: str,
    template_context: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> Any:
    prepared = _escape_literal_delimiters(value)
    if "{%" in prepared or "%}" in prepared or "{#" in prepared:
        _append_invalid_expression(errors, path=path, expression=value)
        return value

    matches = list(_PLACEHOLDER_RE.finditer(prepared))
    if _has_unmatched_delimiters(prepared, matches):
        _append_invalid_expression(errors, path=path, expression=value)
        return value
    if not matches:
        return _restore_literal_delimiters(prepared)

    exact_match = _EXACT_PLACEHOLDER_RE.fullmatch(prepared)
    if exact_match is not None and len(matches) == 1:
        resolved = _resolve_expression(
            exact_match.group(1),
            path=path,
            template_context=template_context,
            errors=errors,
        )
        return deepcopy(resolved.value) if resolved.found else value

    pieces: list[str] = []
    position = 0
    for match in matches:
        pieces.append(prepared[position : match.start()])
        resolved = _resolve_expression(
            match.group(1),
            path=path,
            template_context=template_context,
            errors=errors,
        )
        pieces.append(
            _embedded_placeholder_value(resolved.value) if resolved.found else match.group(0)
        )
        position = match.end()
    pieces.append(prepared[position:])
    return _restore_literal_delimiters("".join(pieces))


@dataclass(frozen=True)
class _ResolvedExpression:
    found: bool
    value: Any = None


def _resolve_expression(
    expression: str,
    *,
    path: str,
    template_context: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> _ResolvedExpression:
    normalized = expression.strip()
    if normalized in _ALLOWED_CONTEXT_PLACEHOLDERS:
        return _lookup_expression(
            normalized, path=path, template_context=template_context, errors=errors
        )
    if normalized.startswith("vars."):
        segments = normalized.split(".")
        if len(segments) != 2 or _IDENTIFIER_RE.fullmatch(segments[1]) is None:
            _append_invalid_expression(errors, path=path, expression=normalized)
            return _ResolvedExpression(False)
        return _lookup_expression(
            normalized, path=path, template_context=template_context, errors=errors
        )
    if "." in normalized:
        namespace = normalized.split(".", 1)[0]
        if namespace not in _ALLOWED_NAMESPACES:
            _append_invalid_expression(errors, path=path, expression=normalized)
            return _ResolvedExpression(False)
    _append_invalid_expression(errors, path=path, expression=normalized or expression)
    return _ResolvedExpression(False)


def _lookup_expression(
    expression: str,
    *,
    path: str,
    template_context: Mapping[str, Any],
    errors: list[dict[str, Any]],
) -> _ResolvedExpression:
    current: object = template_context
    for segment in expression.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            _append_missing_value(errors, path=path, expression=expression)
            return _ResolvedExpression(False)
        current = current[segment]
    return _ResolvedExpression(True, deepcopy(current))


def _validate_payload_safety(
    payload: object,
    *,
    field: str,
    errors: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return deepcopy(validate_runtime_input_payload_safety(payload, field=field))
    except ApiError as exc:
        errors.extend(_api_error_details(exc))
        return None


def _api_error_details(exc: ApiError) -> list[dict[str, Any]]:
    details = [dict(detail) for detail in exc.details]
    if not details:
        details = [{"field": "input", "issue": exc.message}]
    for detail in details:
        detail.setdefault("code", exc.code)
    return details


def _append_invalid_expression(
    errors: list[dict[str, Any]],
    *,
    path: str,
    expression: str,
) -> None:
    errors.append(
        {
            "field": path,
            "issue": f"Unsupported scheduled input placeholder expression {expression!r}",
            "code": SCHEDULE_TEMPLATE_INVALID_EXPRESSION,
            "expression": expression,
        }
    )


def _append_missing_value(
    errors: list[dict[str, Any]],
    *,
    path: str,
    expression: str,
) -> None:
    errors.append(
        {
            "field": path,
            "issue": f"Missing scheduled input placeholder value for {expression!r}",
            "code": SCHEDULE_TEMPLATE_MISSING_VALUE,
            "expression": expression,
        }
    )


def _first_error_code(errors: list[dict[str, Any]]) -> str | None:
    for error in errors:
        code = error.get("code")
        if isinstance(code, str) and code:
            return code
    return None


def _embedded_placeholder_value(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _escape_literal_delimiters(value: str) -> str:
    escaped_literals = _ESCAPED_LITERAL_RE.sub(_escaped_literal_replacement, value)
    return escaped_literals.replace(r"\{{", _ESCAPED_OPEN).replace(r"\}}", _ESCAPED_CLOSE)


def _escaped_literal_replacement(match: re.Match[str]) -> str:
    literal = match.group(1)
    if literal.endswith("\\"):
        literal = literal[:-1]
    return f"{_ESCAPED_OPEN}{literal}{_ESCAPED_CLOSE}"


def _restore_literal_delimiters(value: str) -> str:
    return value.replace(_ESCAPED_OPEN, "{{").replace(_ESCAPED_CLOSE, "}}")


def _has_unmatched_delimiters(value: str, matches: list[re.Match[str]]) -> bool:
    remaining: list[str] = []
    position = 0
    for match in matches:
        remaining.append(value[position : match.start()])
        position = match.end()
    remaining.append(value[position:])
    unmatched = "".join(remaining)
    return "{{" in unmatched or "}}" in unmatched


def _last_run_context(last_run: ScheduledInputLastRunContext | None) -> dict[str, Any]:
    if last_run is None:
        return {}
    context: dict[str, Any] = {}
    _set_if_not_none(context, "id", last_run.id)
    _set_if_not_none(context, "status", last_run.status)
    _set_if_not_none(context, "completedAt", _optional_utc_isoformat(last_run.completed_at))
    return context


def _set_if_not_none(target: dict[str, Any], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value


def _utc_isoformat(value: datetime) -> str:
    return to_utc(value).isoformat().replace("+00:00", "Z")


def _optional_utc_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc_isoformat(value)


def _local_date(value: datetime, timezone_name: str) -> str | None:
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return None
    return to_utc(value).astimezone(timezone).date().isoformat()


def _join_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{key!r}]"


__all__ = [
    "SCHEDULE_RENDER_VALIDATION_FAILED",
    "SCHEDULE_TEMPLATE_INVALID_EXPRESSION",
    "SCHEDULE_TEMPLATE_MISSING_VALUE",
    "ScheduledInputLastRunContext",
    "ScheduledInputRenderPreview",
    "ScheduledInputTemplateRenderResult",
    "build_scheduled_input_template_context",
    "render_and_validate_scheduled_input_template",
    "render_scheduled_input_template",
    "require_scheduled_input_render_ready",
]
