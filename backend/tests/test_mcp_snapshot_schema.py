from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.mcp_server import McpToolSnapshot

_SCHEMA_HASH = "sha256:" + "a" * 64


def _strict_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 20},
        },
        "required": ["ticker", "limit"],
        "additionalProperties": False,
    }


def _snapshot_payload() -> dict[str, object]:
    return {
        "mcpServerKey": "market_data",
        "mcpServerVersion": 3,
        "frozenToolKey": "market_data@3:market_data_lookup",
        "originalToolName": "market.data/lookup-price",
        "openaiFunctionName": "market_data_lookup",
        "schemaHash": _SCHEMA_HASH,
        "strictSchema": _strict_schema(),
        "reverseMapping": {"market_data_lookup": "market.data/lookup-price"},
    }


def test_mcp_tool_snapshot_serializes_publish_time_contract_fields() -> None:
    snapshot = McpToolSnapshot.model_validate(_snapshot_payload())

    payload = snapshot.model_dump(by_alias=True, mode="json")

    assert payload == _snapshot_payload()
    assert "headers" not in payload
    assert "env" not in payload


@pytest.mark.parametrize(
    "field_name",
    [
        "originalToolName",
        "openaiFunctionName",
        "schemaHash",
        "strictSchema",
        "reverseMapping",
        "mcpServerKey",
        "mcpServerVersion",
        "frozenToolKey",
    ],
)
def test_mcp_tool_snapshot_rejects_missing_required_fields(field_name: str) -> None:
    payload = _snapshot_payload()
    del payload[field_name]

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "openai_function_name",
    ["market-data-lookup", "1_market_data_lookup", "market.data.lookup", "a" * 129],
)
def test_mcp_tool_snapshot_rejects_invalid_openai_function_names(
    openai_function_name: str,
) -> None:
    payload = _snapshot_payload()
    payload["openaiFunctionName"] = openai_function_name
    payload["frozenToolKey"] = f"market_data@3:{openai_function_name}"
    payload["reverseMapping"] = {openai_function_name: "market.data/lookup-price"}

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "schema_hash",
    ["a" * 64, "sha256:" + "A" * 64, "sha256:" + "g" * 64, "sha256:" + "a" * 63],
)
def test_mcp_tool_snapshot_rejects_invalid_schema_hashes(schema_hash: str) -> None:
    payload = _snapshot_payload()
    payload["schemaHash"] = schema_hash

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "strict_schema",
    [
        {"type": "string"},
        {"type": "object", "properties": {}, "required": []},
        {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"ticker": {"$ref": "#/defs/Ticker"}},
            "required": ["ticker"],
            "additionalProperties": False,
        },
    ],
)
def test_mcp_tool_snapshot_rejects_malformed_strict_schemas(
    strict_schema: dict[str, object],
) -> None:
    payload = _snapshot_payload()
    payload["strictSchema"] = strict_schema

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


def test_mcp_tool_snapshot_rejects_non_object_strict_schema_payload() -> None:
    payload = _snapshot_payload()
    payload["strictSchema"] = ["not", "an", "object"]

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


@pytest.mark.parametrize(
    "reverse_mapping",
    [
        {"market.data/lookup-price": "market_data_lookup"},
        {"market_data_lookup": "other.tool"},
        {},
        "market_data_lookup",
    ],
)
def test_mcp_tool_snapshot_rejects_malformed_reverse_mappings(
    reverse_mapping: object,
) -> None:
    payload = _snapshot_payload()
    payload["reverseMapping"] = reverse_mapping

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)


def test_mcp_tool_snapshot_rejects_frozen_tool_key_without_snapshot_identity() -> None:
    payload = _snapshot_payload()
    payload["frozenToolKey"] = "other_server@3:other_tool"

    with pytest.raises(ValidationError):
        _ = McpToolSnapshot.model_validate(payload)
