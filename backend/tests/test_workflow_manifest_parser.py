from __future__ import annotations

import pytest

from app.schemas.workflow_manifest import WorkflowManifestDiagnostic
from app.services.workflow_manifest_parser import parse_workflow_manifest


def _valid_manifest_source(*, uses: str = "research_agent@1") -> str:
    return f"""apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
  description: Runs research before producing the final slot output.
inputSchema:
  type: object
  properties:
    ticker:
      type: string
  required:
    - ticker
  additionalProperties: false
steps:
  - id: research
    agents:
      - slot: analysis
        uses: {uses}
        with:
          ticker: ${{{{ inputs.ticker }}}}
  - id: decision
    agents:
      - slot: final
        uses: decision_agent@2
        with:
          analysis: ${{{{ steps.research.outputs.analysis.summary }}}}
output:
  from: ${{{{ steps.decision.outputs.final }}}}
"""


def _single_diagnostic(source: str) -> WorkflowManifestDiagnostic:
    result = parse_workflow_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    assert diagnostic.path
    assert diagnostic.line is not None
    assert diagnostic.column is not None
    return diagnostic


def test_parse_valid_workflow_manifest_returns_typed_manifest() -> None:
    result = parse_workflow_manifest(_valid_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.api_version == "ledger.workflow/v1"
    assert result.manifest.kind == "Workflow"
    assert result.manifest.metadata.key == "market_review"
    assert result.manifest.steps[0].id == "research"
    assert result.manifest.steps[0].agents[0].uses.key == "research_agent"
    assert result.manifest.steps[0].agents[0].uses.version == 1
    assert result.manifest.steps[1].agents[0].inputs["analysis"].step_id == "research"

    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    assert dumped["apiVersion"] == "ledger.workflow/v1"
    assert dumped["steps"][0]["agents"][0]["uses"] == "research_agent@1"
    assert dumped["steps"][1]["agents"][0]["with"]["analysis"] == (
        "${{ steps.research.outputs.analysis.summary }}"
    )


def test_parser_rejects_malformed_yaml_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: [broken
"""
    )

    assert diagnostic.path == "$"
    assert "Malformed YAML" in diagnostic.message


def test_parser_rejects_duplicate_yaml_keys_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: ledger.workflow/v1
apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  key: market_review
  name: Market Review
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
"""
    )

    assert diagnostic.path == "$"
    assert "Duplicate mapping key" in diagnostic.message


@pytest.mark.parametrize(
    ("source", "expected_message"),
    [
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata: &metadata
  key: market_review
  name: Market Review
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML anchors are not supported",
        ),
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata: *metadata
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML aliases are not supported",
        ),
        (
            """apiVersion: ledger.workflow/v1
kind: Workflow
metadata:
  <<: {key: market_review, name: Market Review}
inputSchema:
  type: object
steps: []
output:
  from: ${{ steps.research.outputs.analysis }}
""",
            "YAML merge keys are not supported",
        ),
    ],
)
def test_parser_rejects_unsupported_yaml_features(
    source: str,
    expected_message: str,
) -> None:
    result = parse_workflow_manifest(source)

    assert result.manifest is None
    assert any(expected_message in diagnostic.message for diagnostic in result.diagnostics)
    assert all(diagnostic.line is not None for diagnostic in result.diagnostics)
    assert all(diagnostic.column is not None for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_message"),
    [
        (
            _valid_manifest_source().replace("apiVersion: ledger.workflow/v1\n", "", 1),
            "apiVersion",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("ledger.workflow/v1", "ledger.workflow/v2", 1),
            "apiVersion",
            "Input should be 'ledger.workflow/v1'",
        ),
        (
            _valid_manifest_source().replace("  name: Market Review\n", "", 1),
            "metadata.name",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("  type: object\n", "  type: string\n", 1),
            "inputSchema",
            "inputSchema must be an object schema",
        ),
    ],
)
def test_parser_returns_schema_validation_diagnostics(
    source: str,
    expected_path: str,
    expected_message: str,
) -> None:
    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert expected_message in diagnostic.message


@pytest.mark.parametrize("uses", ["research_agent@latest", "research_agent", "research_agent@1.2"])
def test_parser_rejects_non_exact_agent_versions(uses: str) -> None:
    diagnostic = _single_diagnostic(_valid_manifest_source(uses=uses))

    assert diagnostic.path == "steps[0].agents[0].uses"
    assert "pin an exact numeric version" in diagnostic.message


def test_parser_rejects_duplicate_step_ids_and_slots_with_manifest_paths() -> None:
    duplicate_step = _valid_manifest_source().replace("  - id: decision", "  - id: research", 1)
    duplicate_step_diagnostic = _single_diagnostic(duplicate_step)

    assert duplicate_step_diagnostic.path == "steps[1].id"
    assert "Duplicate step id" in duplicate_step_diagnostic.message

    duplicate_slot = _valid_manifest_source().replace(
        "      - slot: analysis\n        uses: research_agent@1",
        "      - slot: analysis\n        uses: research_agent@1\n"
        + "      - slot: analysis\n        uses: review_agent@3",
        1,
    )
    duplicate_slot_diagnostic = _single_diagnostic(duplicate_slot)

    assert duplicate_slot_diagnostic.path == "steps[0].agents[1].slot"
    assert "Duplicate slot name within the same step" in duplicate_slot_diagnostic.message


def test_parser_rejects_invalid_step_references_and_optional_final_output() -> None:
    forward_reference = _valid_manifest_source().replace(
        "${{ steps.research.outputs.analysis.summary }}",
        "${{ steps.decision.outputs.final.summary }}",
    )
    forward_diagnostic = _single_diagnostic(forward_reference)

    assert forward_diagnostic.path == "steps[1].agents[0].with.analysis"
    assert "Step references must point to an earlier step" in forward_diagnostic.message

    optional_output = _valid_manifest_source().replace(
        "        uses: decision_agent@2",
        "        uses: decision_agent@2\n        optional: true",
    )
    optional_output_diagnostic = _single_diagnostic(optional_output)

    assert optional_output_diagnostic.path == "output.from"
    assert "Final output cannot reference an optional slot" in optional_output_diagnostic.message
