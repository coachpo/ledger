from __future__ import annotations

from datetime import date
from types import SimpleNamespace


def test_runner_parses_positions_renders_report_and_builds_trade_decisions() -> None:
    from app.langgraph.runner import (
        BacktestLangGraphRequest,
        BacktestLangGraphRunner,
        LangGraphSymbolAnalysis,
    )

    class FakeAnalyzer:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_report)
            self.calls.append((symbol, position_quantity))
            if symbol == "AAPL":
                return LangGraphSymbolAnalysis(label="BUY", summary="Momentum is improving.")
            return LangGraphSymbolAnalysis(label="UNDERWEIGHT", summary="Risk is elevated.")

    runner = BacktestLangGraphRunner(analyzer=FakeAnalyzer())

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=42,
            cycle_date=date(2024, 6, 17),
            prompt_report_slug="prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-06-17)\n\n"
                "## System\n"
                "Today is 2024-06-17.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Balances:\n"
                "- Cash: 10000.00 USD (DEPOSIT)\n"
                "Positions:\n"
                "- AAPL: 5 shares @ 180.00 USD\n"
                "- MSFT: 2 shares @ 410.00 USD\n\n"
                "Prior reports:\n"
                "- None"
            ),
        )
    )

    assert result.report_content == (
        "# LangGraph Analysis\n\n"
        "- Backtest ID: 42\n"
        "- Cycle date: 2024-06-17\n"
        "- Prompt report slug: prompt_report\n\n"
        "## AAPL\n"
        "- Label: BUY\n"
        "- Held quantity: 5\n"
        "- Summary: Momentum is improving.\n\n"
        "## MSFT\n"
        "- Label: UNDERWEIGHT\n"
        "- Held quantity: 2\n"
        "- Summary: Risk is elevated."
    )
    assert [
        (decision.symbol, decision.action, decision.quantity) for decision in result.decisions
    ] == [
        ("AAPL", "BUY", 1),
        ("MSFT", "SELL", 2),
    ]


def test_seeded_runner_smoke_executes_seeded_agents_and_topology() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import (
        SEEDED_AGENT_SPECS,
        SEEDED_TOPOLOGY,
        build_seeded_langgraph_runner,
    )

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_report, position_quantity)
            return LangGraphSymbolAnalysis(label="HOLD", summary=f"Keep {symbol} unchanged.")

    runner = build_seeded_langgraph_runner(analyzer=FakeAnalyzer())

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=99,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="seeded_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## System\n"
                "Today is 2024-07-01.\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert [agent.key for agent in SEEDED_AGENT_SPECS] == [
        "position_analyst",
        "risk_reviewer",
        "decision_writer",
    ]
    assert SEEDED_TOPOLOGY.key == "seeded_internal_backtest_v1"
    assert SEEDED_TOPOLOGY.agent_order == ("position_analyst", "decision_writer")
    assert "Topology: seeded_internal_backtest_v1" in result.report_content
    assert "Agents: position_analyst, decision_writer" in result.report_content
    assert [
        (decision.symbol, decision.action, decision.quantity) for decision in result.decisions
    ] == [("NVDA", "HOLD", None)]


def test_analyst_reviewer_pattern_applies_conservative_review_before_decisions() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_report, position_quantity)
            return LangGraphSymbolAnalysis(label="BUY", summary=f"Add to {symbol}.")

    runner = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    )

    result = runner.run_cycle(
        BacktestLangGraphRequest(
            backtest_id=100,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="reviewer_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert "Topology: analyst_reviewer_v1" in result.report_content
    assert "Agents: position_analyst, risk_reviewer, decision_writer" in result.report_content
    assert "Conservative review applied: BUY -> HOLD" in result.report_content
    assert [
        (decision.symbol, decision.action, decision.quantity, decision.reasoning)
        for decision in result.decisions
    ] == [
        (
            "NVDA",
            "HOLD",
            None,
            "HOLD: Add to NVDA. Conservative review applied: BUY -> HOLD.",
        )
    ]


def test_seeded_and_reviewer_patterns_diverge_on_same_input() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (cycle_date, prompt_report, position_quantity)
            return LangGraphSymbolAnalysis(label="BUY", summary=f"Add to {symbol}.")

    request = BacktestLangGraphRequest(
        backtest_id=101,
        cycle_date=date(2024, 7, 1),
        prompt_report_slug="paired_prompt_report",
        prompt_report=(
            "# Cycle Prompt (2024-07-01)\n\n"
            "## User\n"
            "Portfolio state:\n"
            "Positions:\n"
            "- NVDA: 3 shares @ 1200.00 USD\n"
        ),
    )

    seeded_result = build_backtest_langgraph_runner(
        pattern_key="seeded_internal_backtest_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(request)
    reviewer_result = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(request)

    assert [(decision.action, decision.quantity) for decision in seeded_result.decisions] == [
        ("BUY", 1)
    ]
    assert [(decision.action, decision.quantity) for decision in reviewer_result.decisions] == [
        ("HOLD", None)
    ]


def test_analyst_reviewer_pattern_converts_overweight_to_hold() -> None:
    from app.langgraph.runner import BacktestLangGraphRequest, LangGraphSymbolAnalysis
    from app.langgraph.seeds import build_backtest_langgraph_runner

    class FakeAnalyzer:
        def analyze_symbol(
            self,
            *,
            symbol: str,
            cycle_date: date,
            prompt_report: str,
            position_quantity: str,
        ) -> LangGraphSymbolAnalysis:
            _ = (symbol, cycle_date, prompt_report, position_quantity)
            return LangGraphSymbolAnalysis(label="OVERWEIGHT", summary="Build the position.")

    result = build_backtest_langgraph_runner(
        pattern_key="analyst_reviewer_v1",
        analyzer=FakeAnalyzer(),
    ).run_cycle(
        BacktestLangGraphRequest(
            backtest_id=102,
            cycle_date=date(2024, 7, 1),
            prompt_report_slug="overweight_prompt_report",
            prompt_report=(
                "# Cycle Prompt (2024-07-01)\n\n"
                "## User\n"
                "Portfolio state:\n"
                "Positions:\n"
                "- NVDA: 3 shares @ 1200.00 USD\n"
            ),
        )
    )

    assert [(decision.action, decision.quantity) for decision in result.decisions] == [
        ("HOLD", None)
    ]
    assert "Conservative review applied: OVERWEIGHT -> HOLD" in result.report_content


def test_live_analyzer_falls_back_when_structured_output_parser_is_incompatible(
    monkeypatch,
) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeStructuredInvoker:
        def invoke(self, messages):
            _ = messages
            raise ValueError(
                "Structured Output response does not have a 'parsed' field nor a 'refusal' field"
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            _ = schema
            return FakeStructuredInvoker()

        def invoke(self, messages):
            _ = messages
            return SimpleNamespace(content='{"label":"HOLD","summary":"Keep NVDA unchanged."}')

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
    )
    monkeypatch.setattr(analyzer, "_get_llm", lambda: FakeLLM())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_report="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "HOLD"
    assert analysis.summary == "Keep NVDA unchanged."


def test_live_analyzer_uses_responses_api_with_explicit_input_format(monkeypatch) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeStructuredInvoker:
        def invoke(self, messages):
            _ = messages
            raise ValueError(
                "Structured Output response does not have a 'parsed' field nor a 'refusal' field"
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            _ = schema
            return FakeStructuredInvoker()

        def invoke(self, messages):
            _ = messages
            return SimpleNamespace(content="")

    captured: dict[str, object] = {}

    class FakeResponsesAPI:
        def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return iter(
                [
                    SimpleNamespace(type="response.output_text.delta", delta='{"label":"BUY",'),
                    SimpleNamespace(
                        type="response.output_text.delta", delta='"summary":"Add NVDA."}'
                    ),
                    SimpleNamespace(
                        type="response.output_text.done",
                        text='{"label":"BUY","summary":"Add NVDA."}',
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(id="resp_test", status="completed"),
                    ),
                ]
            )

    class FakeOpenAIClient:
        def __init__(self) -> None:
            self.responses = FakeResponsesAPI()

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
        api_mode="responses",
    )
    monkeypatch.setattr(analyzer, "_get_llm", lambda: FakeLLM())
    monkeypatch.setattr(analyzer, "_get_openai_client", lambda: FakeOpenAIClient())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_report="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "BUY"
    assert analysis.summary == "Add NVDA."
    assert captured["kwargs"] == {
        "model": "gpt-5.4-mini",
        "reasoning": {"effort": "none"},
        "stream": True,
        "text": {"format": {"type": "json_object"}},
        "input": [
            {
                "type": "message",
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You analyze one held portfolio position for a historical backtest. "
                            "Use only the information provided in the prompt report. "
                            "Do not invent data from after the cycle date. "
                            "Return a normalized label and a concise summary. "
                            'Respond as JSON with keys "label" and "summary".'
                        ),
                    }
                ],
            },
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Cycle date: 2024-07-01\n"
                            "Held symbol: NVDA\n"
                            "Held quantity: 3\n\n"
                            "Full prompt report:\n"
                            "# Prompt"
                        ),
                    }
                ],
            },
        ],
    }


def test_live_analyzer_normalizes_lowercase_label_from_streamed_responses(monkeypatch) -> None:
    from app.langgraph.runner import LiveBacktestSymbolAnalyzer

    class FakeResponsesAPI:
        def create(self, **kwargs):
            _ = kwargs
            return iter(
                [
                    SimpleNamespace(
                        type="response.output_text.done",
                        text='{"label":"hold","summary":"Keep NVDA unchanged."}',
                    ),
                    SimpleNamespace(
                        type="response.completed",
                        response=SimpleNamespace(id="resp_test", status="completed"),
                    ),
                ]
            )

    class FakeOpenAIClient:
        def __init__(self) -> None:
            self.responses = FakeResponsesAPI()

    analyzer = LiveBacktestSymbolAnalyzer(
        model="gpt-5.4-mini",
        api_key="test-key",
        base_url="http://example.test/v1",
        timeout_seconds=30.0,
        temperature=0.0,
        api_mode="responses",
    )
    monkeypatch.setattr(analyzer, "_get_openai_client", lambda: FakeOpenAIClient())

    analysis = analyzer.analyze_symbol(
        symbol="NVDA",
        cycle_date=date(2024, 7, 1),
        prompt_report="# Prompt",
        position_quantity="3",
    )

    assert analysis.label == "HOLD"
    assert analysis.summary == "Keep NVDA unchanged."
