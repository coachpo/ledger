from __future__ import annotations

import pytest

from app.schemas.agent_manifest import AgentManifestDiagnostic
from app.services.agent_manifest_parser import parse_agent_manifest


def _valid_manifest_source(*, output_schema: str = "research_summary@3") -> str:
    return f"""apiVersion: signaldeck.agent/v1
kind: Agent
metadata:
  key: research_agent
  name: Research Agent
  description: Produces a structured research summary.
spec:
  modelConnection: primary_openai
  systemPrompt: |
    You are a research analyst.
    Return concise output.
  inputSchema:
    type: object
    additionalProperties: false
    properties:
      ticker:
        type: string
    required:
      - ticker
  outputSchema: {output_schema}
  capabilities:
    - sec_filing_lookup@2
  mcpServers:
    - market_data@1
"""


def _single_diagnostic(source: str) -> AgentManifestDiagnostic:
    result = parse_agent_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.severity == "error"
    assert diagnostic.path
    assert diagnostic.line is not None
    assert diagnostic.column is not None
    return diagnostic


def test_parse_valid_agent_manifest_returns_typed_manifest() -> None:
    result = parse_agent_manifest(_valid_manifest_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.api_version == "signaldeck.agent/v1"
    assert result.manifest.kind == "Agent"
    assert result.manifest.metadata.key == "research_agent"
    assert result.manifest.spec.model_connection == "primary_openai"
    assert result.manifest.spec.output_schema.key == "research_summary"
    assert result.manifest.spec.output_schema.version == 3

    dumped = result.manifest.model_dump(mode="json", by_alias=True)
    assert dumped["spec"]["outputSchema"] == "research_summary@3"
    assert dumped["spec"]["capabilities"] == ["sec_filing_lookup@2"]
    assert "skills" not in dumped["spec"]
    assert dumped["spec"]["mcpServers"] == ["market_data@1"]


def test_parse_rejects_unsupported_skills_manifest() -> None:
    source = _valid_manifest_source().replace("  capabilities:", "  skills:", 1)

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.skills"
    assert "spec.skills is not supported in agent manifests" in diagnostic.message


def test_parse_rejects_capabilities_and_unsupported_skills_together() -> None:
    source = _valid_manifest_source().replace(
        "  capabilities:\n    - sec_filing_lookup@2\n",
        "  capabilities:\n    - sec_filing_lookup@2\n  skills:\n    - sec_filing_lookup@2\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.skills"
    assert "spec.skills is not supported in agent manifests" in diagnostic.message


def test_parser_rejects_malformed_yaml_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: signaldeck.agent/v1
kind: Agent
metadata:
  key: [broken
"""
    )

    assert diagnostic.path == "$"
    assert "Malformed YAML" in diagnostic.message


def test_parser_rejects_duplicate_yaml_keys_with_location() -> None:
    diagnostic = _single_diagnostic(
        """apiVersion: signaldeck.agent/v1
apiVersion: signaldeck.agent/v1
kind: Agent
metadata:
  key: research_agent
  name: Research Agent
spec:
  modelConnection: primary_openai
  systemPrompt: Test
  inputSchema:
    type: object
  outputSchema: research_summary@3
"""
    )

    assert diagnostic.path == "$"
    assert "Duplicate mapping key" in diagnostic.message


@pytest.mark.parametrize(
    ("source", "expected_message"),
    [
        (
            _valid_manifest_source().replace("metadata:\n", "metadata: &metadata\n", 1),
            "YAML anchors are not supported",
        ),
        (
            _valid_manifest_source().replace("spec:\n", "extra: *metadata\nspec:\n", 1),
            "YAML aliases are not supported",
        ),
        (
            _valid_manifest_source().replace(
                "metadata:\n  key: research_agent\n  name: Research Agent\n",
                "metadata:\n  <<: {key: research_agent, name: Research Agent}\n",
                1,
            ),
            "YAML merge keys are not supported",
        ),
        (
            _valid_manifest_source().replace("name: Research Agent", "name: !secret value", 1),
            "YAML tag",
        ),
    ],
)
def test_parser_rejects_unsupported_yaml_features(
    source: str,
    expected_message: str,
) -> None:
    result = parse_agent_manifest(source)

    assert result.manifest is None
    assert any(expected_message in diagnostic.message for diagnostic in result.diagnostics)
    assert all(diagnostic.line is not None for diagnostic in result.diagnostics)
    assert all(diagnostic.column is not None for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    ("source", "expected_path", "expected_message"),
    [
        (
            _valid_manifest_source().replace("  key: research_agent\n", "", 1),
            "metadata.key",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("signaldeck.agent/v1", "signaldeck.agent/v2", 1),
            "apiVersion",
            "Input should be 'signaldeck.agent/v1'",
        ),
        (
            _valid_manifest_source().replace("  modelConnection: primary_openai\n", "", 1),
            "spec.modelConnection",
            "Field required",
        ),
        (
            _valid_manifest_source().replace("    type: object\n", "    type: string\n", 1),
            "spec.inputSchema",
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


def test_parser_rejects_raw_model_connection_id_field() -> None:
    source = _valid_manifest_source().replace(
        "  modelConnection: primary_openai\n",
        "  modelConnectionId: 1\n",
        1,
    )

    result = parse_agent_manifest(source)

    assert result.manifest is None
    assert any(diagnostic.path == "spec.modelConnection" for diagnostic in result.diagnostics)
    assert any(
        diagnostic.path == "spec.modelConnectionId"
        and "Extra inputs are not permitted" in diagnostic.message
        for diagnostic in result.diagnostics
    )


@pytest.mark.parametrize("output_schema", ["research_summary@latest", "research_summary", "1@2"])
def test_parser_rejects_invalid_pin_syntax(output_schema: str) -> None:
    diagnostic = _single_diagnostic(_valid_manifest_source(output_schema=output_schema))

    assert diagnostic.path == "spec.outputSchema"
    assert "pin an exact numeric version" in diagnostic.message


def test_parser_rejects_duplicate_refs_with_manifest_paths() -> None:
    source = _valid_manifest_source().replace(
        "  capabilities:\n    - sec_filing_lookup@2\n",
        "  capabilities:\n    - sec_filing_lookup@2\n    - sec_filing_lookup@2\n",
        1,
    )
    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.capabilities[1]"
    assert "Duplicate capability selection" in diagnostic.message


__all__ = ["_valid_manifest_source"]
