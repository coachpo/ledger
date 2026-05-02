from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Protocol, cast

import pytest

from app.schemas.workflow import WorkflowCreate
from app.schemas.workflow_manifest import WorkflowManifestDiagnostic
from app.services.workflow_manifest_examples import (
    TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE,
)
from app.services.workflow_manifest_parser import parse_workflow_manifest


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
    return f"""apiVersion: ledger.workflow/v1
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


def test_compile_tradingagents_fixed_unrolled_manifest_preserves_sequential_topology() -> None:
    payload = compile_workflow_manifest(TRADINGAGENTS_FIXED_UNROLLED_WORKFLOW_MANIFEST_SOURCE)

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
