from __future__ import annotations

from functools import lru_cache

from app.agents.runtime_tools.positions import (
    POSITION_LOOKUP_OPENAI_FUNCTION_NAME,
    POSITION_LOOKUP_TOOL_SPEC,
    execute_position_lookup,
    parse_position_lookup_arguments,
)
from app.agents.runtime_tools.registry import RuntimeToolRegistry
from app.agents.runtime_tools.reports import (
    REPORT_LOOKUP_OPENAI_FUNCTION_NAME,
    REPORT_LOOKUP_TOOL_SPEC,
    execute_report_lookup,
    parse_report_lookup_arguments,
)
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec

RUNTIME_TOOL_SPECS = (REPORT_LOOKUP_TOOL_SPEC, POSITION_LOOKUP_TOOL_SPEC)


@lru_cache
def get_default_runtime_tool_registry() -> RuntimeToolRegistry:
    return RuntimeToolRegistry(RUNTIME_TOOL_SPECS)


__all__ = [
    "POSITION_LOOKUP_OPENAI_FUNCTION_NAME",
    "POSITION_LOOKUP_TOOL_SPEC",
    "REPORT_LOOKUP_OPENAI_FUNCTION_NAME",
    "REPORT_LOOKUP_TOOL_SPEC",
    "RUNTIME_TOOL_SPECS",
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolRegistry",
    "RuntimeToolSpec",
    "execute_position_lookup",
    "execute_report_lookup",
    "get_default_runtime_tool_registry",
    "parse_position_lookup_arguments",
    "parse_report_lookup_arguments",
]
