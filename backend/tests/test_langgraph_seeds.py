from __future__ import annotations

from datetime import date

import pytest

from app.langgraph.seeds import (
    ANALYST_REVIEWER_PATTERN_MENTION_POLICY,
    ANALYST_REVIEWER_PATTERN_SPEC,
    ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC,
    ANALYST_REVIEWER_TOPOLOGY,
    DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY,
    SEED_PATTERN_MENTION_POLICY,
    SEEDED_BUILTIN_REGISTRY,
    SEEDED_BUILTIN_SPECS,
    SEEDED_PATTERN_SPEC,
    SEEDED_TOOL_ENABLED_PATTERN_SPEC,
    SEEDED_TOPOLOGY,
    build_backtest_langgraph_runner,
    get_backtest_pattern_spec,
    get_seeded_capability_bundle_spec,
    get_seeded_connector_spec,
    get_seeded_tool_spec,
    is_supported_backtest_orchestration_pattern_key,
    list_supported_backtest_orchestration_pattern_keys,
)


def test_seeded_builtin_specs_expose_plain_handles_while_registry_stays_canonical() -> None:
    assert tuple(spec.handle for spec in SEEDED_BUILTIN_SPECS) == ("librarian", "explore")
    assert set(SEEDED_BUILTIN_REGISTRY) == {"builtin:librarian", "builtin:explore"}
    assert SEEDED_BUILTIN_REGISTRY["builtin:librarian"].handle == "librarian"
    assert SEEDED_BUILTIN_REGISTRY["builtin:librarian"].display_name == "Librarian"
    assert SEEDED_BUILTIN_REGISTRY["builtin:librarian"].capability_bundle_keys == (
        "builtin.librarian_context",
    )
    assert SEEDED_BUILTIN_REGISTRY["builtin:explore"].handle == "explore"
    assert SEEDED_BUILTIN_REGISTRY["builtin:explore"].display_name == "Explore"
    assert SEEDED_BUILTIN_REGISTRY["builtin:explore"].capability_bundle_keys == (
        "builtin.explore_context",
    )


def test_seeded_pattern_mention_policy_defines_allowed_builtins() -> None:
    assert SEED_PATTERN_MENTION_POLICY.version == 1
    assert SEED_PATTERN_MENTION_POLICY.allow_characters is False
    assert SEED_PATTERN_MENTION_POLICY.allowed_builtin_handles == ("librarian", "explore")


def test_analyst_reviewer_pattern_mention_policy_remains_reviewer_specific() -> None:
    assert ANALYST_REVIEWER_PATTERN_MENTION_POLICY.version == 1
    assert ANALYST_REVIEWER_PATTERN_MENTION_POLICY.allow_characters is True
    assert ANALYST_REVIEWER_PATTERN_MENTION_POLICY.allowed_builtin_handles == (
        "librarian",
        "explore",
    )


def test_supported_backtest_orchestration_pattern_keys_include_baseline_and_plan_b_keys() -> None:
    assert DEFAULT_BACKTEST_ORCHESTRATION_PATTERN_KEY == "seeded_internal_backtest_v1"
    assert SEEDED_TOPOLOGY.key == "seeded_internal_backtest_v1"
    assert ANALYST_REVIEWER_TOPOLOGY.key == "analyst_reviewer_v1"
    assert list_supported_backtest_orchestration_pattern_keys() == (
        "seeded_internal_backtest_v1",
        "analyst_reviewer_v1",
        "seeded_internal_backtest_tool_enabled_v1",
        "analyst_reviewer_tool_enabled_v1",
    )
    assert is_supported_backtest_orchestration_pattern_key("seeded_internal_backtest_v1") is True
    assert is_supported_backtest_orchestration_pattern_key("analyst_reviewer_v1") is True
    assert (
        is_supported_backtest_orchestration_pattern_key("seeded_internal_backtest_tool_enabled_v1")
        is True
    )
    assert (
        is_supported_backtest_orchestration_pattern_key("analyst_reviewer_tool_enabled_v1") is True
    )


def test_baseline_pattern_specs_remain_structured_output_only() -> None:
    assert SEEDED_PATTERN_SPEC.key == "seeded_internal_backtest_v1"
    assert SEEDED_PATTERN_SPEC.topology is SEEDED_TOPOLOGY
    assert SEEDED_PATTERN_SPEC.execution_mode == "structured_output"
    assert SEEDED_PATTERN_SPEC.default_tool_ids == ()
    assert SEEDED_PATTERN_SPEC.allowed_bundle_keys == ()
    assert SEEDED_PATTERN_SPEC.connector_ids == ()

    assert ANALYST_REVIEWER_PATTERN_SPEC.key == "analyst_reviewer_v1"
    assert ANALYST_REVIEWER_PATTERN_SPEC.topology is ANALYST_REVIEWER_TOPOLOGY
    assert ANALYST_REVIEWER_PATTERN_SPEC.execution_mode == "structured_output"
    assert ANALYST_REVIEWER_PATTERN_SPEC.default_tool_ids == ()
    assert ANALYST_REVIEWER_PATTERN_SPEC.allowed_bundle_keys == ()
    assert ANALYST_REVIEWER_PATTERN_SPEC.connector_ids == ()


def test_tool_enabled_pattern_specs_extend_baseline_topologies_without_mutation() -> None:
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.topology is SEEDED_TOPOLOGY
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.execution_mode == "tool_enabled"
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.default_tool_ids == (
        "ledger.report_lookup",
        "ledger.orchestration_catalog_lookup",
        "ledger.cycle_context_lookup",
    )
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.allowed_bundle_keys == (
        "builtin.librarian_context",
        "builtin.explore_context",
    )
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.connector_ids == ()

    assert ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.topology is ANALYST_REVIEWER_TOPOLOGY
    assert ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.execution_mode == "tool_enabled"
    assert ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.default_tool_ids == (
        "ledger.report_lookup",
        "ledger.orchestration_catalog_lookup",
        "ledger.cycle_context_lookup",
    )
    assert ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.allowed_bundle_keys == (
        "builtin.librarian_context",
        "builtin.explore_context",
    )
    assert ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.connector_ids == ()


def test_tool_enabled_pattern_bundle_ceiling_matches_seeded_builtin_bundle_refs() -> None:
    seeded_builtin_bundle_keys = tuple(
        dict.fromkeys(
            bundle_key
            for builtin in SEEDED_BUILTIN_SPECS
            for bundle_key in builtin.capability_bundle_keys
        )
    )

    assert seeded_builtin_bundle_keys == (
        "builtin.librarian_context",
        "builtin.explore_context",
    )
    assert SEEDED_TOOL_ENABLED_PATTERN_SPEC.allowed_bundle_keys == seeded_builtin_bundle_keys
    assert (
        ANALYST_REVIEWER_TOOL_ENABLED_PATTERN_SPEC.allowed_bundle_keys == seeded_builtin_bundle_keys
    )
    for bundle_key in seeded_builtin_bundle_keys:
        assert get_seeded_capability_bundle_spec(bundle_key) is not None


def test_seeded_phase_one_tool_registry_is_deterministic_and_read_only() -> None:
    report_lookup = get_seeded_tool_spec("ledger.report_lookup")
    assert report_lookup is not None
    assert report_lookup.display_name == "Report Lookup"
    assert report_lookup.revision == 1

    orchestration_lookup = get_seeded_tool_spec("ledger.orchestration_catalog_lookup")
    assert orchestration_lookup is not None
    assert orchestration_lookup.display_name == "Orchestration Catalog Lookup"
    assert orchestration_lookup.revision == 1

    cycle_context_lookup = get_seeded_tool_spec("ledger.cycle_context_lookup")
    assert cycle_context_lookup is not None
    assert cycle_context_lookup.display_name == "Cycle Context Lookup"
    assert cycle_context_lookup.revision == 1


def test_seeded_phase_two_builtin_bundle_refs_expand_to_seeded_tool_metadata() -> None:
    librarian_bundle = get_seeded_capability_bundle_spec("builtin.librarian_context")
    assert librarian_bundle is not None
    assert librarian_bundle.display_name == "Builtin Librarian Context"
    assert librarian_bundle.tool_ids == (
        "ledger.report_lookup",
        "ledger.orchestration_catalog_lookup",
    )
    assert librarian_bundle.revision == 1

    explore_bundle = get_seeded_capability_bundle_spec("builtin.explore_context")
    assert explore_bundle is not None
    assert explore_bundle.display_name == "Builtin Explore Context"
    assert explore_bundle.tool_ids == (
        "ledger.orchestration_catalog_lookup",
        "ledger.cycle_context_lookup",
    )
    assert explore_bundle.revision == 1


def test_seeded_phase_three_connector_placeholders_have_deterministic_registry_entries() -> None:
    market_data_connector = get_seeded_connector_spec("ledger.mcp.market_data")
    assert market_data_connector is not None
    assert market_data_connector.display_name == "Trusted Market Data MCP"
    assert market_data_connector.transport == "mcp"
    assert market_data_connector.lifecycle == "placeholder"
    assert market_data_connector.revision == 1

    company_filings_connector = get_seeded_connector_spec("ledger.mcp.company_filings")
    assert company_filings_connector is not None
    assert company_filings_connector.display_name == "Trusted Company Filings MCP"
    assert company_filings_connector.transport == "mcp"
    assert company_filings_connector.lifecycle == "placeholder"
    assert company_filings_connector.revision == 1


def test_unknown_seeded_capability_metadata_fails_closed() -> None:
    assert get_backtest_pattern_spec("seeded_internal_backtest_tool_enabled_v999") is None
    assert get_seeded_tool_spec("ledger.unknown_tool") is None
    assert get_seeded_capability_bundle_spec("builtin.unknown_context") is None
    assert get_seeded_connector_spec("ledger.mcp.unknown") is None


@pytest.mark.parametrize(
    ("pattern_key", "expected_agent_keys", "expected_review_mode"),
    [
        (
            "seeded_internal_backtest_v1",
            ("position_analyst", "decision_writer"),
            "none",
        ),
        (
            "analyst_reviewer_v1",
            ("position_analyst", "risk_reviewer", "decision_writer"),
            "conservative",
        ),
        (
            "seeded_internal_backtest_tool_enabled_v1",
            ("position_analyst", "decision_writer"),
            "none",
        ),
        (
            "analyst_reviewer_tool_enabled_v1",
            ("position_analyst", "risk_reviewer", "decision_writer"),
            "conservative",
        ),
    ],
)
def test_build_backtest_langgraph_runner_supports_supported_pattern_keys(
    pattern_key: str,
    expected_agent_keys: tuple[str, ...],
    expected_review_mode: str,
) -> None:
    from app.langgraph.runner import LangGraphSymbolAnalysis

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="HOLD", summary="No-op analyzer")

    runner = build_backtest_langgraph_runner(
        pattern_key=pattern_key,
        analyzer=FakeAnalyzer(),
    )

    assert runner.topology_key == pattern_key
    assert runner.agent_keys == expected_agent_keys
    assert runner.review_mode == expected_review_mode


def test_build_backtest_langgraph_runner_rejects_unsupported_pattern_key() -> None:
    from app.langgraph.runner import LangGraphSymbolAnalysis

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_text: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_text, position_quantity)
            return LangGraphSymbolAnalysis(label="HOLD", summary="No-op analyzer")

    with pytest.raises(
        ValueError,
        match="Unknown orchestration pattern: unsupported_pattern",
    ):
        build_backtest_langgraph_runner(
            pattern_key="unsupported_pattern",
            analyzer=FakeAnalyzer(),
        )
