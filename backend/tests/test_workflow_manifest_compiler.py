from __future__ import annotations

import json
from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

import pytest

from app.schemas.workflow import WorkflowCreate
from app.schemas.workflow_manifest import WorkflowManifestDiagnostic
from app.services.workflow_manifest_parser import parse_workflow_manifest
from tests.test_workflow_manifest_parser import (
    GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
    GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
)


class _CompilerError(Protocol):
    diagnostics: list[WorkflowManifestDiagnostic]


class _CompilerModule(Protocol):
    WorkflowManifestCompilerError: type[Exception]
    compile_workflow_manifest: Callable[[object], dict[str, object]]


_raw_compiler_module = cast(object, import_module("app.services.workflow_manifest_compiler"))
_compiler = cast(_CompilerModule, _raw_compiler_module)
WorkflowManifestCompilerError = _compiler.WorkflowManifestCompilerError
compile_workflow_manifest = _compiler.compile_workflow_manifest


def _manifest_source(
    *,
    output_reference: str = "${{ steps.synthesize.outputs.decision.recommendation }}",
) -> str:
    return f"""apiVersion: signaldeck.workflow/v1
kind: Workflow
metadata:
  key: analyst_workflow
  name: Analyst Workflow
  description: Runs parallel research before synthesizing a decision.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
    horizon_days:
      type: integer
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: research_agent@7
        with:
          ticker: ${{{{ inputs.ticker }}}}
          horizon_days: ${{{{ inputs.horizon_days }}}}
      - slot: context
        uses: context_agent@3
        optional: true
        with:
          ticker: ${{{{ inputs.ticker }}}}
  - id: synthesize
    agents:
      - slot: decision
        uses: decision_agent@12
        with:
          analysis: ${{{{ steps.research.outputs.analysis }}}}
          summary: ${{{{ steps.research.outputs.analysis.summary }}}}
          context_summary: ${{{{ steps.research.outputs.context.summary }}}}
output:
  from: {output_reference}
"""


def _current_workflow_payload() -> dict[str, object]:
    return {
        "key": "analyst_workflow",
        "name": "Analyst Workflow",
        "description": "Runs parallel research before synthesizing a decision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "horizon_days": {"type": "integer"},
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
        "steps": [
            {
                "index": 1,
                "agents": [
                    {
                        "agentKey": "research_agent",
                        "agentVersion": 7,
                        "slot": "analysis",
                        "wiring": {
                            "ticker": {"from": "input", "path": "ticker"},
                            "horizon_days": {"from": "input", "path": "horizon_days"},
                        },
                        "optional": False,
                    },
                    {
                        "agentKey": "context_agent",
                        "agentVersion": 3,
                        "slot": "context",
                        "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        "optional": True,
                    },
                ],
            },
            {
                "index": 2,
                "agents": [
                    {
                        "agentKey": "decision_agent",
                        "agentVersion": 12,
                        "slot": "decision",
                        "wiring": {
                            "analysis": {"from": "step", "stepIndex": 1, "slot": "analysis"},
                            "summary": {
                                "from": "step",
                                "stepIndex": 1,
                                "slot": "analysis",
                                "path": "summary",
                            },
                            "context_summary": {
                                "from": "step",
                                "stepIndex": 1,
                                "slot": "context",
                                "path": "summary",
                            },
                        },
                        "optional": False,
                    }
                ],
            },
        ],
        "outputSpec": {
            "kind": "slot",
            "stepIndex": 2,
            "slot": "decision",
            "path": "recommendation",
        },
    }


def test_compile_workflow_manifest_source_matches_current_workflow_payload() -> None:
    payload = compile_workflow_manifest(_manifest_source())

    assert payload == _current_workflow_payload()
    assert (
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_workflow_manifest_accepts_validated_manifest() -> None:
    result = parse_workflow_manifest(_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert compile_workflow_manifest(result.manifest) == _current_workflow_payload()


def test_backward_compat_compile_workflow_manifest_keeps_agent_only_steps() -> None:
    payload = compile_workflow_manifest(_manifest_source())
    steps = cast(list[dict[str, object]], payload["steps"])

    assert payload == _current_workflow_payload()
    assert all("agents" in step for step in steps)
    assert all("operations" not in step for step in steps)


def test_compile_workflow_manifest_preserves_input_schema_metadata() -> None:
    source = _manifest_source().replace(
        """inputSchema:
  type: object
  properties:
    ticker:
      type: string
    horizon_days:
      type: integer
  required:
    - ticker
  additionalProperties: false
""",
        """inputSchema:
  type: object
  title: Workflow request
  description: Inputs collected before workflow execution.
  properties:
    ticker:
      type: string
      title: Ticker symbol
      description: Public market ticker to research.
    horizon_days:
      type: integer
      title: Horizon days
      description: Optional number of days to assess.
    price_targets:
      type: array
      title: Price targets
      description: Optional candidate price targets.
      items:
        type: number
        title: Price target
        description: Candidate target price.
    signal:
      title: Signal
      description: Discriminated signal branch.
      anyOf:
        - type: object
          title: Bullish signal
          description: Bullish branch payload.
          properties:
            kind:
              const: bullish
            score:
              type: integer
          required:
            - kind
            - score
          additionalProperties: false
        - type: object
          title: Bearish signal
          description: Bearish branch payload.
          properties:
            kind:
              const: bearish
            reason:
              type: string
          required:
            - kind
            - reason
          additionalProperties: false
      discriminator:
        propertyName: kind
  required:
    - ticker
    - signal
  additionalProperties: false
""",
        1,
    )

    payload = compile_workflow_manifest(source)

    input_schema = cast(dict[str, object], payload["inputSchema"])
    properties = cast(dict[str, dict[str, object]], input_schema["properties"])
    price_targets = properties["price_targets"]
    price_items = cast(dict[str, object], price_targets["items"])
    signal = properties["signal"]
    signal_variants = cast(list[dict[str, object]], signal["anyOf"])

    assert input_schema["title"] == "Workflow request"
    assert input_schema["description"] == "Inputs collected before workflow execution."
    assert properties["ticker"]["title"] == "Ticker symbol"
    assert properties["horizon_days"]["description"] == "Optional number of days to assess."
    assert "horizon_days" not in cast(list[str], input_schema["required"])
    assert price_targets["description"] == "Optional candidate price targets."
    assert price_items["title"] == "Price target"
    assert signal["title"] == "Signal"
    assert signal_variants[0]["title"] == "Bullish signal"
    assert signal_variants[1]["description"] == "Bearish branch payload."
    assert (
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_workflow_manifest_preserves_valid_input_schema_defaults() -> None:
    source = _manifest_source().replace(
        """    ticker:
      type: string
    horizon_days:
      type: integer
""",
        """    ticker:
      type: string
      default: NVDA
    horizon_days:
      type: integer
      default: 30
""",
        1,
    )

    payload = compile_workflow_manifest(source)

    input_schema = cast(dict[str, object], payload["inputSchema"])
    properties = cast(dict[str, dict[str, object]], input_schema["properties"])
    assert properties["ticker"]["default"] == "NVDA"
    assert properties["horizon_days"]["default"] == 30
    assert "horizon_days" not in cast(list[str], input_schema["required"])
    assert (
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )


def test_compile_workflow_manifest_rejects_invalid_input_schema_default_with_property_path() -> (
    None
):
    source = _manifest_source().replace(
        """    ticker:
      type: string
""",
        """    ticker:
      type: string
      default: 123
""",
        1,
    )

    with pytest.raises(WorkflowManifestCompilerError) as excinfo:
        _ = compile_workflow_manifest(source)

    compiler_error = cast(_CompilerError, cast(object, excinfo.value))
    assert any(
        diagnostic.path == "inputSchema.properties.ticker.default"
        and "Default value must match schema type 'string'" in diagnostic.message
        for diagnostic in compiler_error.diagnostics
    )


def test_compile_workflow_manifest_omits_output_path_when_reference_has_no_path() -> None:
    payload = compile_workflow_manifest(
        _manifest_source(output_reference="${{ steps.synthesize.outputs.decision }}")
    )

    assert payload["outputSpec"] == {
        "kind": "slot",
        "stepIndex": 2,
        "slot": "decision",
    }


def test_compile_workflow_manifest_source_raises_parser_diagnostics() -> None:
    source = _manifest_source().replace("uses: research_agent@7", "uses: research_agent@latest")

    with pytest.raises(WorkflowManifestCompilerError) as excinfo:
        _ = compile_workflow_manifest(source)

    compiler_error = cast(_CompilerError, cast(object, excinfo.value))
    assert len(compiler_error.diagnostics) == 1
    diagnostic = compiler_error.diagnostics[0]
    assert diagnostic.path == "steps[0].agents[0].uses"
    assert "pin an exact numeric version" in diagnostic.message


def test_compile_platform_graph_fixed_unrolled_manifest_preserves_sequential_topology() -> None:
    payload = compile_workflow_manifest(GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE)

    assert (
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == payload
    )
    steps = cast(list[dict[str, object]], payload["steps"])
    assert [step["index"] for step in steps] == list(range(1, 12))
    analyst_agents = cast(list[dict[str, object]], steps[0]["agents"])
    assert [agent["slot"] for agent in analyst_agents] == [
        "market_report",
        "social_sentiment_report",
        "news_report",
        "fundamentals_report",
    ]
    assert all(
        cast(dict[str, object], source)["from"] == "input"
        for agent in analyst_agents
        for source in cast(dict[str, object], agent["wiring"]).values()
    )

    bear_round_one = cast(list[dict[str, object]], steps[2]["agents"])[0]
    assert cast(dict[str, object], bear_round_one["wiring"])["priorState"] == {
        "from": "step",
        "stepIndex": 2,
        "slot": "bull",
        "path": "nextState",
    }
    research_manager = cast(list[dict[str, object]], steps[5]["agents"])[0]
    assert cast(dict[str, object], research_manager["wiring"])["debateState"] == {
        "from": "step",
        "stepIndex": 5,
        "slot": "bear",
        "path": "nextState",
    }
    neutral_risk = cast(list[dict[str, object]], steps[8]["agents"])[0]
    assert cast(dict[str, object], neutral_risk["wiring"])["priorState"] == {
        "from": "step",
        "stepIndex": 8,
        "slot": "aggressive",
        "path": "nextState",
    }
    assert payload["outputSpec"] == {"kind": "slot", "stepIndex": 11, "slot": "decision"}


def _compiled_steps(payload: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], payload["steps"])


def _compiled_agents(step: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], step["agents"])


def _compiled_wiring(agent: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], agent["wiring"])


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _v2_manifest_source(*, flow: str, output_reference: str) -> str:
    return f"""apiVersion: signaldeck.workflow/v2
kind: Workflow
metadata:
  key: market_review_v2
  name: Market Review V2
  description: V2 graph workflow.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
    horizon_days:
      type: integer
  required:
    - ticker
  additionalProperties: false
flow:
{flow}
output:
  from: {output_reference}
"""


def _compiled_graph(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["compiledGraph"])


def _workflow_core_payload(payload: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if key != "compiledGraph"}


def test_compile_workflow_manifest_v1_regression_payload_is_byte_stable() -> None:
    first_payload = compile_workflow_manifest(_manifest_source())
    second_payload = compile_workflow_manifest(_manifest_source())

    assert first_payload == _current_workflow_payload()
    assert _canonical_json(first_payload) == _canonical_json(second_payload)


def test_compile_v2_root_step_emits_core_payload_and_compiled_graph() -> None:
    payload = compile_workflow_manifest(
        _v2_manifest_source(
            flow="""  kind: step
  id: research
  slot: analysis
  uses: research_agent@1
  with:
    ticker: ${{ inputs.ticker }}""",
            output_reference="${{ nodes.research.outputs.analysis.summary }}",
        )
    )

    core_payload = _workflow_core_payload(payload)
    assert (
        WorkflowCreate.model_validate(core_payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == core_payload
    )
    assert _compiled_steps(payload) == [
        {
            "index": 1,
            "agents": [
                {
                    "agentKey": "research_agent",
                    "agentVersion": 1,
                    "slot": "analysis",
                    "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                    "optional": False,
                }
            ],
        }
    ]
    assert payload["outputSpec"] == {
        "kind": "slot",
        "stepIndex": 1,
        "slot": "analysis",
        "path": "summary",
    }
    assert _compiled_graph(payload)["rootNodeId"] == "research"


def test_compile_v2_sequence_and_fanout_preserve_deterministic_execution_shape() -> None:
    payload = compile_workflow_manifest(
        _v2_manifest_source(
            flow="""  kind: sequence
  id: root_sequence
  nodes:
    - kind: fanout
      id: analyst_fanout
      branches:
        - id: market
          node:
            kind: step
            id: market_analysis
            slot: market_report
            uses: market_agent@1
            with:
              ticker: ${{ inputs.ticker }}
        - id: news
          node:
            kind: step
            id: news_analysis
            slot: news_report
            uses: news_agent@2
            with:
              ticker: ${{ inputs.ticker }}
    - kind: step
      id: decision
      slot: final
      uses: decision_agent@3
      with:
        marketReport: ${{ nodes.analyst_fanout.outputs.market_report }}
        newsReport: ${{ nodes.analyst_fanout.outputs.news_report }}""",
            output_reference="${{ nodes.root_sequence.outputs.final }}",
        )
    )

    steps = _compiled_steps(payload)
    assert [step["index"] for step in steps] == [1, 2]
    assert [agent["agentKey"] for agent in _compiled_agents(steps[0])] == [
        "market_agent",
        "news_agent",
    ]
    decision_wiring = _compiled_wiring(_compiled_agents(steps[1])[0])
    assert decision_wiring["marketReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "market_report",
    }
    assert decision_wiring["newsReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "news_report",
    }
    graph = _compiled_graph(payload)
    assert _canonical_json(payload) == _canonical_json(
        compile_workflow_manifest(
            _v2_manifest_source(
                flow="""  kind: sequence
  id: root_sequence
  nodes:
    - kind: fanout
      id: analyst_fanout
      branches:
        - id: market
          node:
            kind: step
            id: market_analysis
            slot: market_report
            uses: market_agent@1
            with:
              ticker: ${{ inputs.ticker }}
        - id: news
          node:
            kind: step
            id: news_analysis
            slot: news_report
            uses: news_agent@2
            with:
              ticker: ${{ inputs.ticker }}
    - kind: step
      id: decision
      slot: final
      uses: decision_agent@3
      with:
        marketReport: ${{ nodes.analyst_fanout.outputs.market_report }}
        newsReport: ${{ nodes.analyst_fanout.outputs.news_report }}""",
                output_reference="${{ nodes.root_sequence.outputs.final }}",
            )
        )
    )
    assert "secret" not in _canonical_json(graph).lower()


def test_compile_v2_fanout_branch_id_output_aliases_branch_step_slot() -> None:
    payload = compile_workflow_manifest(
        _v2_manifest_source(
            flow="""  kind: fanout
  id: analyst_fanout
  branches:
    - id: market
      node:
        kind: step
        id: market_analysis
        slot: analysis
        uses: market_agent@1
        with:
          ticker: ${{ inputs.ticker }}""",
            output_reference="${{ nodes.analyst_fanout.outputs.market }}",
        )
    )

    assert payload["outputSpec"] == {"kind": "slot", "stepIndex": 1, "slot": "analysis"}
    assert _compiled_graph(payload)["output"] == {
        "source": "nodes",
        "nodeId": "analyst_fanout",
        "slot": "market",
        "stepIndex": 1,
        "compiledSlot": "analysis",
        "sourceNodeId": "market_analysis",
        "sourceSlot": "analysis",
    }


def test_compile_v2_loop_expands_to_declared_iteration_bound() -> None:
    payload = compile_workflow_manifest(
        _v2_manifest_source(
            flow="""  kind: loop
  id: review_loop
  maxIterations: 2
  sequence:
    kind: sequence
    id: review_sequence
    nodes:
      - kind: step
        id: risk_review
        slot: risk
        uses: risk_agent@1
        with:
          ticker: ${{ inputs.ticker }}""",
            output_reference="${{ nodes.review_loop.outputs.risk }}",
        )
    )

    steps = _compiled_steps(payload)
    assert [step["index"] for step in steps] == [1, 2]
    assert payload["outputSpec"] == {"kind": "slot", "stepIndex": 2, "slot": "risk"}
    loop_iterations = [
        node.get("loopIteration")
        for node in cast(list[dict[str, object]], _compiled_graph(payload)["nodes"])
        if node.get("kind") == "step"
    ]
    assert loop_iterations == [1, 2]


def test_compile_v2_loop_state_refs_carry_previous_iteration_output() -> None:
    payload = compile_workflow_manifest(
        _v2_manifest_source(
            flow="""  kind: loop
  id: state_loop
  maxIterations: 2
  state:
    state: ${{ inputs.initial_state }}
  sequence:
    kind: sequence
    id: state_sequence
    nodes:
      - kind: step
        id: state_update
        slot: state
        uses: state_agent@1
        with:
          priorState: ${{ inputs.initial_state }}""",
            output_reference="${{ nodes.state_loop.outputs.state }}",
        )
    )

    steps = _compiled_steps(payload)
    first_wiring = _compiled_wiring(_compiled_agents(steps[0])[0])
    second_wiring = _compiled_wiring(_compiled_agents(steps[1])[0])
    graph_nodes = cast(list[dict[str, object]], _compiled_graph(payload)["nodes"])
    loop_node = next(node for node in graph_nodes if node.get("nodeId") == "state_loop")
    iteration_step_refs = [
        cast(dict[str, object], node["refs"])["priorState"]
        for node in graph_nodes
        if node.get("nodeId") == "state_update" and node.get("kind") == "step"
    ]

    assert loop_node["stateRefs"] == {"state": {"source": "inputs", "path": "initial_state"}}
    assert first_wiring["priorState"] == {"from": "input", "path": "initial_state"}
    assert second_wiring["priorState"] == {"from": "step", "stepIndex": 1, "slot": "state"}
    assert iteration_step_refs == [
        {"source": "inputs", "path": "initial_state"},
        {
            "source": "nodes",
            "nodeId": "state_update",
            "slot": "state",
            "stepIndex": 1,
            "compiledSlot": "state",
            "sourceNodeId": "state_update",
            "sourceSlot": "state",
        },
    ]


def test_compile_v2_source_raises_parser_diagnostics() -> None:
    source = _v2_manifest_source(
        flow="""  kind: step
  id: research
  slot: analysis
  uses: research_agent@1
  with:
    prior: ${{ nodes.research.outputs.analysis }}""",
        output_reference="${{ nodes.research.outputs.analysis }}",
    )

    with pytest.raises(WorkflowManifestCompilerError) as excinfo:
        _ = compile_workflow_manifest(source)

    compiler_error = cast(_CompilerError, cast(object, excinfo.value))
    assert len(compiler_error.diagnostics) == 1
    assert compiler_error.diagnostics[0].path == "flow.with.prior"
    assert "Node references must point to an earlier node" in compiler_error.diagnostics[0].message


@pytest.mark.parametrize(
    ("source", "expected_key", "expected_step_count", "expected_output_spec"),
    [
        (
            GENERIC_PLATFORM_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_fixed_unrolled_review",
            11,
            {"kind": "slot", "stepIndex": 11, "slot": "decision"},
        ),
        (
            GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_strict_sequential_review",
            14,
            {"kind": "slot", "stepIndex": 14, "slot": "decision"},
        ),
        (
            GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_practical_fanout_review",
            11,
            {"kind": "slot", "stepIndex": 11, "slot": "decision"},
        ),
    ],
)
def test_compile_platform_graph_v1_example_manifests_have_expected_counts_and_output_spec(
    source: str,
    expected_key: str,
    expected_step_count: int,
    expected_output_spec: dict[str, object],
) -> None:
    payload = compile_workflow_manifest(source)

    steps = _compiled_steps(payload)
    assert payload["key"] == expected_key
    assert len(steps) == expected_step_count
    assert [step["index"] for step in steps] == list(range(1, expected_step_count + 1))
    assert payload["outputSpec"] == expected_output_spec


def test_compile_platform_graph_strict_sequential_manifest_preserves_ordered_analyst_steps() -> (
    None
):
    payload = compile_workflow_manifest(
        GENERIC_PLATFORM_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE
    )

    steps = _compiled_steps(payload)
    analyst_agents = [_compiled_agents(step)[0] for step in steps[:4]]
    debate_agents = [_compiled_agents(step)[0] for step in steps[4:]]
    first_bull_wiring = _compiled_wiring(debate_agents[0])

    assert [len(_compiled_agents(step)) for step in steps[:4]] == [1, 1, 1, 1]
    assert [agent["agentKey"] for agent in analyst_agents] == [
        "market_analyst",
        "social_analyst",
        "news_analyst",
        "fundamentals_analyst",
    ]
    assert [agent["agentKey"] for agent in debate_agents] == [
        "bull_researcher",
        "bear_researcher",
        "bull_researcher",
        "bear_researcher",
        "research_manager",
        "trader",
        "aggressive_risk_analyst",
        "neutral_risk_analyst",
        "conservative_risk_analyst",
        "portfolio_manager",
    ]
    assert first_bull_wiring["marketReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "market_report",
    }
    assert first_bull_wiring["socialSentimentReport"] == {
        "from": "step",
        "stepIndex": 2,
        "slot": "social_sentiment_report",
    }
    assert first_bull_wiring["newsReport"] == {
        "from": "step",
        "stepIndex": 3,
        "slot": "news_report",
    }
    assert first_bull_wiring["fundamentalsReport"] == {
        "from": "step",
        "stepIndex": 4,
        "slot": "fundamentals_report",
    }
    assert _compiled_wiring(debate_agents[7])["priorState"] == {
        "from": "step",
        "stepIndex": 11,
        "slot": "aggressive",
        "path": "nextState",
    }


def test_compile_platform_graph_practical_fanout_manifest_preserves_analyst_fanout() -> None:
    payload = compile_workflow_manifest(
        GENERIC_PLATFORM_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE
    )

    steps = _compiled_steps(payload)
    analyst_agents = _compiled_agents(steps[0])
    debate_agents = [_compiled_agents(step)[0] for step in steps[1:]]
    first_bull_wiring = _compiled_wiring(debate_agents[0])

    assert [agent["agentKey"] for agent in analyst_agents] == [
        "market_analyst",
        "social_analyst",
        "news_analyst",
        "fundamentals_analyst",
    ]
    assert all(
        cast(dict[str, object], source)["from"] == "input"
        for agent in analyst_agents
        for source in _compiled_wiring(agent).values()
    )
    assert [agent["agentKey"] for agent in debate_agents[:4]] == [
        "bull_researcher",
        "bear_researcher",
        "bull_researcher",
        "bear_researcher",
    ]
    assert first_bull_wiring["marketReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "market_report",
    }
    assert first_bull_wiring["socialSentimentReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "social_sentiment_report",
    }
    assert first_bull_wiring["newsReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "news_report",
    }
    assert first_bull_wiring["fundamentalsReport"] == {
        "from": "step",
        "stepIndex": 1,
        "slot": "fundamentals_report",
    }
    assert _compiled_wiring(debate_agents[1])["priorState"] == {
        "from": "step",
        "stepIndex": 2,
        "slot": "bull",
        "path": "nextState",
    }


@pytest.mark.parametrize(
    ("source", "expected_key", "expected_step_count", "expected_first_step_slots"),
    [
        (
            GENERIC_PLATFORM_V2_STRICT_SEQUENTIAL_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_strict_sequential_review",
            17,
            ["market_report"],
        ),
        (
            GENERIC_PLATFORM_V2_PRACTICAL_FANOUT_REVIEW_WORKFLOW_MANIFEST_SOURCE,
            "platform_graph_v2_practical_fanout_review",
            14,
            ["market_report", "social_sentiment_report", "news_report", "fundamentals_report"],
        ),
    ],
)
def test_compile_platform_graph_v2_examples_emit_graph_loops_memory_and_secret_free_payload(
    source: str,
    expected_key: str,
    expected_step_count: int,
    expected_first_step_slots: list[str],
) -> None:
    payload = compile_workflow_manifest(source)
    core_payload = _workflow_core_payload(payload)
    graph = _compiled_graph(payload)

    assert (
        WorkflowCreate.model_validate(core_payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        == core_payload
    )
    assert payload["key"] == expected_key
    steps = _compiled_steps(payload)
    assert [step["index"] for step in steps] == list(range(1, expected_step_count + 1))
    assert [agent["slot"] for agent in _compiled_agents(steps[0])] == expected_first_step_slots
    assert payload["outputSpec"] == {
        "kind": "slot",
        "stepIndex": expected_step_count,
        "slot": "decision",
    }

    graph_nodes = cast(list[dict[str, object]], graph["nodes"])
    loop_nodes = [node for node in graph_nodes if node["kind"] == "loop"]
    loop_iterations = [
        node.get("loopIteration")
        for node in graph_nodes
        if node.get("loopId") == "investment_debate_loop" and node.get("kind") == "step"
    ]
    memory = cast(dict[str, object], graph["postRunMemory"])
    source_refs = cast(dict[str, object], memory["sourceRefs"])

    assert graph["apiVersion"] == "signaldeck.workflow/v2"
    assert [node["nodeId"] for node in loop_nodes] == ["investment_debate_loop", "risk_debate_loop"]
    assert [node["maxIterations"] for node in loop_nodes] == [2, 2]
    assert loop_iterations == [1, 1, 2, 2]
    assert source_refs["action"] == {
        "source": "nodes",
        "nodeId": "portfolio_manager",
        "slot": "decision",
        "stepIndex": expected_step_count,
        "compiledSlot": "decision",
        "sourceNodeId": "portfolio_manager",
        "sourceSlot": "decision",
        "path": "action",
    }
    assert memory["benchmarkSymbol"] == {"source": "inputs", "path": "benchmarkSymbol"}
    serialized_payload = _canonical_json(payload)
    assert "sk-" not in serialized_payload
    assert "apiKey" not in serialized_payload
    assert "secret" not in serialized_payload.lower()
