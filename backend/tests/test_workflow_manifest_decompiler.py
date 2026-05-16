# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services.workflow_manifest_compiler import compile_workflow_manifest
from app.services.workflow_manifest_decompiler import (
    WorkflowManifestDecompilerError,
    decompile_workflow_manifest,
)
from app.services.workflow_manifest_parser import parse_workflow_manifest


@dataclass(frozen=True)
class _WorkflowRow:
    key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    steps: list[dict[str, Any]]
    output_spec: dict[str, Any]


def _workflow_payload() -> dict[str, Any]:
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
                        "agentId": 101,
                        "outputSchemaId": 201,
                        "outputSchemaVersion": 7,
                        "wiring": {
                            "ticker": {"from": "input", "path": "ticker"},
                            "horizon_days": {"from": "input", "path": "horizon_days"},
                        },
                        "optional": False,
                        "budgetUsd": "0.10000000",
                    },
                    {
                        "agentKey": "context_agent",
                        "agentVersion": 3,
                        "slot": "context",
                        "agentId": 102,
                        "outputSchemaId": 202,
                        "outputSchemaVersion": 3,
                        "wiring": {"ticker": {"from": "input", "path": "ticker"}},
                        "optional": True,
                        "budgetUsd": "0.05000000",
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
                        "agentId": 103,
                        "outputSchemaId": 203,
                        "outputSchemaVersion": 12,
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
                        "budgetUsd": "0.20000000",
                    }
                ],
            },
        ],
        "outputSpec": {
            "kind": "slot",
            "stepIndex": 2,
            "slot": "decision",
            "path": "recommendation",
            "agentId": 103,
            "agentKey": "decision_agent",
            "agentVersion": 12,
            "outputSchemaId": 203,
            "outputSchemaVersion": 12,
        },
    }


def _workflow_row(payload: dict[str, Any]) -> _WorkflowRow:
    return _WorkflowRow(
        key=payload["key"],
        name=payload["name"],
        description=payload["description"],
        input_schema=payload["inputSchema"],
        steps=payload["steps"],
        output_spec=payload["outputSpec"],
    )


def _current_write_payload(payload: dict[str, Any]) -> dict[str, object]:
    return {
        "key": payload["key"],
        "name": payload["name"],
        "description": payload["description"],
        "inputSchema": payload["inputSchema"],
        "steps": [
            {
                "index": step["index"],
                "agents": [
                    {
                        "agentKey": agent["agentKey"],
                        "agentVersion": agent["agentVersion"],
                        "slot": agent["slot"],
                        "wiring": agent["wiring"],
                        "optional": agent["optional"],
                    }
                    for agent in step["agents"]
                ],
            }
            for step in payload["steps"]
        ],
        "outputSpec": {
            key: value
            for key, value in payload["outputSpec"].items()
            if key in {"kind", "stepIndex", "slot", "path"}
        },
    }


def test_decompile_workflow_manifest_round_trips_stored_payload_to_canonical_yaml() -> None:
    payload = _workflow_payload()
    result = decompile_workflow_manifest(_workflow_row(payload))
    parsed = parse_workflow_manifest(result.source)

    assert result.source.startswith("apiVersion: signaldeck.workflow/v1\nkind: Workflow\n")
    assert parsed.diagnostics == []
    assert parsed.manifest is not None
    assert parsed.manifest.steps[0].id == "step_1"
    assert parsed.manifest.steps[1].agents[0].inputs["summary"].expression == (
        "${{ steps.step_1.outputs.analysis.summary }}"
    )
    assert compile_workflow_manifest(result.source) == _current_write_payload(payload)
    assert result.payload == _current_write_payload(payload)


def test_decompile_workflow_manifest_omits_runtime_only_fields_and_false_optional() -> None:
    result = decompile_workflow_manifest(_workflow_row(_workflow_payload()))

    assert "agentId" not in result.source
    assert "outputSchemaId" not in result.source
    assert "budgetUsd" not in result.source
    assert "optional: false" not in result.source
    assert "optional: true" in result.source


def test_decompile_workflow_manifest_rejects_lossy_unsupported_output_kind() -> None:
    payload = _workflow_payload()
    payload["outputSpec"] = {**payload["outputSpec"], "kind": "agent"}

    with pytest.raises(WorkflowManifestDecompilerError):
        _ = decompile_workflow_manifest(_workflow_row(payload), verify_lossless=False)
