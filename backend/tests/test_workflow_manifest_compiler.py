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
