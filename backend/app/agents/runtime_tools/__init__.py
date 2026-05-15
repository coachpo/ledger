from __future__ import annotations

from functools import lru_cache

from app.agents.runtime_tools.market_data import (
    FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME,
    FUNDAMENTALS_LOOKUP_TOOL_SPEC,
    INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME,
    INDICATORS_LOOKUP_TOOL_SPEC,
    INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME,
    INSIDER_DATA_LOOKUP_TOOL_SPEC,
    MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC,
    MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC,
    MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME,
    MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC,
    NEWS_LOOKUP_OPENAI_FUNCTION_NAME,
    NEWS_LOOKUP_TOOL_SPEC,
    SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME,
    SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC,
    execute_fundamentals_lookup,
    execute_history_lookup,
    execute_indicators_lookup,
    execute_insider_data_lookup,
    execute_news_lookup,
    execute_ohlcv_lookup,
    execute_quote_lookup,
    execute_social_sentiment_lookup,
    parse_fundamentals_lookup_arguments,
    parse_history_lookup_arguments,
    parse_indicators_lookup_arguments,
    parse_insider_data_lookup_arguments,
    parse_news_lookup_arguments,
    parse_ohlcv_lookup_arguments,
    parse_quote_lookup_arguments,
    parse_social_sentiment_lookup_arguments,
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
from app.extensions.registry import (
    get_bundled_extension_registry,
    load_extension_contribution_registrar,
)


def _load_runtime_tool_specs() -> tuple[RuntimeToolSpec, ...]:
    specs: list[RuntimeToolSpec] = []
    for extension in get_bundled_extension_registry().list_extensions():
        if extension.scaffold is None:
            continue
        for registrar in extension.scaffold.runtime_executors:
            for contribution in load_extension_contribution_registrar(registrar.registrar):
                if not isinstance(contribution, RuntimeToolSpec):
                    message = (
                        f"Runtime tool registrar {registrar.registrar!r} returned "
                        + f"unsupported contribution {type(contribution).__name__!r}"
                    )
                    raise ValueError(message)
                specs.append(contribution)
    return tuple(specs)


RUNTIME_TOOL_SPECS = _load_runtime_tool_specs()


@lru_cache
def get_default_runtime_tool_registry() -> RuntimeToolRegistry:
    return RuntimeToolRegistry(RUNTIME_TOOL_SPECS)


__all__ = [
    "FUNDAMENTALS_LOOKUP_OPENAI_FUNCTION_NAME",
    "FUNDAMENTALS_LOOKUP_TOOL_SPEC",
    "INDICATORS_LOOKUP_OPENAI_FUNCTION_NAME",
    "INDICATORS_LOOKUP_TOOL_SPEC",
    "INSIDER_DATA_LOOKUP_OPENAI_FUNCTION_NAME",
    "INSIDER_DATA_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_HISTORY_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_HISTORY_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_OHLCV_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_OHLCV_LOOKUP_TOOL_SPEC",
    "MARKET_DATA_QUOTE_LOOKUP_OPENAI_FUNCTION_NAME",
    "MARKET_DATA_QUOTE_LOOKUP_TOOL_SPEC",
    "NEWS_LOOKUP_OPENAI_FUNCTION_NAME",
    "NEWS_LOOKUP_TOOL_SPEC",
    "SOCIAL_SENTIMENT_LOOKUP_OPENAI_FUNCTION_NAME",
    "SOCIAL_SENTIMENT_LOOKUP_TOOL_SPEC",
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
    "execute_fundamentals_lookup",
    "execute_history_lookup",
    "execute_indicators_lookup",
    "execute_insider_data_lookup",
    "execute_news_lookup",
    "execute_ohlcv_lookup",
    "execute_position_lookup",
    "execute_social_sentiment_lookup",
    "execute_quote_lookup",
    "execute_report_lookup",
    "execute_report_memory_write",
    "get_default_runtime_tool_registry",
    "parse_fundamentals_lookup_arguments",
    "parse_history_lookup_arguments",
    "parse_indicators_lookup_arguments",
    "parse_insider_data_lookup_arguments",
    "parse_news_lookup_arguments",
    "parse_ohlcv_lookup_arguments",
    "parse_position_lookup_arguments",
    "parse_quote_lookup_arguments",
    "parse_social_sentiment_lookup_arguments",
    "parse_report_lookup_arguments",
    "parse_report_memory_write_arguments",
]
