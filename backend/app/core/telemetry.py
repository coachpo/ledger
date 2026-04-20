from __future__ import annotations

import importlib
from threading import Lock
from typing import Any

_LOGFIRE_CONFIG_LOCK = Lock()
_LOGFIRE_CONFIGURED = False


def _get_logfire_module() -> Any:
    return importlib.import_module("logfire")


def configure_logfire() -> None:
    global _LOGFIRE_CONFIGURED
    if _LOGFIRE_CONFIGURED:
        return

    with _LOGFIRE_CONFIG_LOCK:
        if _LOGFIRE_CONFIGURED:
            return

        logfire = _get_logfire_module()
        logfire.configure(
            service_name="ledger-backend",
            send_to_logfire="if-token-present",
            console=False,
            inspect_arguments=False,
        )
        _LOGFIRE_CONFIGURED = True


def create_logfire_span(message_template: str, /, **attributes: Any) -> Any:
    configure_logfire()
    logfire = _get_logfire_module()
    return logfire.span(message_template, **attributes)


def format_current_trace_id(span: Any) -> str | None:
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


def format_current_span_id(span: Any) -> str | None:
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.span_id, "016x")
