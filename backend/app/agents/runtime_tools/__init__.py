from __future__ import annotations

from functools import lru_cache

from app.agents.runtime_tools.market_data import (
    MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    execute_history_lookup,
    execute_quote_lookup,
    parse_history_lookup_arguments,
    parse_quote_lookup_arguments,
)
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
    REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME,
    REPORT_MEMORY_WRITE_TOOL_SPEC,
    execute_report_lookup,
    execute_report_memory_write,
    parse_report_lookup_arguments,
    parse_report_memory_write_arguments,
)
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec

RUNTIME_TOOL_SPECS = (
    REPORT_LOOKUP_TOOL_SPEC,
    REPORT_MEMORY_WRITE_TOOL_SPEC,
    POSITION_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
)


@lru_cache
def get_default_runtime_tool_registry() -> RuntimeToolRegistry:
    return RuntimeToolRegistry(RUNTIME_TOOL_SPECS)


__all__ = [
    "MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC",
    "POSITION_LOOKUP_OPENAI_FUNCTION_NAME",
    "POSITION_LOOKUP_TOOL_SPEC",
    "REPORT_LOOKUP_OPENAI_FUNCTION_NAME",
    "REPORT_LOOKUP_TOOL_SPEC",
    "REPORT_MEMORY_WRITE_OPENAI_FUNCTION_NAME",
    "REPORT_MEMORY_WRITE_TOOL_SPEC",
    "RUNTIME_TOOL_SPECS",
    "RuntimeToolContext",
    "RuntimeToolError",
    "RuntimeToolRegistry",
    "RuntimeToolSpec",
    "execute_history_lookup",
    "execute_position_lookup",
    "execute_quote_lookup",
    "execute_report_lookup",
    "execute_report_memory_write",
    "get_default_runtime_tool_registry",
    "parse_history_lookup_arguments",
    "parse_position_lookup_arguments",
    "parse_quote_lookup_arguments",
    "parse_report_lookup_arguments",
    "parse_report_memory_write_arguments",
]
