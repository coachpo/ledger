from __future__ import annotations

from typing import Any, cast

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from tests.fixtures.workflow_manifests import base_manifest_data, dump_manifest


def http_node_package_source(
    *,
    method: str = "POST",
    package_key: str = "http_callbacks",
    response_json_schema: dict[str, Any] | None = None,
) -> str:
    return dump_manifest(
        _http_node_manifest_data(
            method=method,
            package_key=package_key,
            response_json_schema=response_json_schema,
        )
    )


def _http_node_manifest_data(
    *,
    method: str = "POST",
    package_key: str = "http_callbacks",
    response_json_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_schema = {
        "type": "object",
        "properties": {
            "webhookUrl": {"type": "string"},
            "ticker": {"type": "string"},
        },
        "required": ["webhookUrl", "ticker"],
    }
    return base_manifest_data(
        package_key=package_key,
        package_name="HTTP Callback Package",
        package_description="Package with a non-agent HTTP callback.",
        input_schema=input_schema,
        output_schema_key="webhook_response",
        output_schemas=[
            {
                "key": "webhook_response",
                "name": "Webhook Response",
                "description": "Response from the callback target.",
                "jsonSchema": response_json_schema or {"type": "object"},
            }
        ],
        agents=[],
        workflows=[
            {
                "key": "notify",
                "name": "Notify",
                "description": "Sends a webhook callback.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "webhookUrl": {"type": "string"},
                        "ticker": {"type": "string"},
                    },
                },
                "flow": {
                    "kind": "http",
                    "id": "notify_slack",
                    "slot": "webhook_result",
                    "method": method,
                    "url": "${{ inputs.webhookUrl }}",
                    "headers": {
                        "Content-Type": "application/json",
                        "Authorization": "${{ secrets.slack_webhook_token }}",
                    },
                    "query": {"ticker": "${{ inputs.ticker }}"},
                    "body": {
                        "ticker": "${{ inputs.ticker }}",
                        "token": "${{ secrets.body_token }}",
                    },
                    "response": {"outputSchema": "webhook_response"},
                    "timeoutSeconds": 10,
                    "optional": False,
                },
                "output": {"from": "${{ nodes.notify_slack.outputs.webhook_result }}"},
            }
        ],
    )


def test_http_node_manifest_compiles_secret_refs_without_secret_values() -> None:
    result = parse_workflow_package_manifest(http_node_package_source())

    assert result.diagnostics == []
    assert result.manifest is not None
    flow = result.manifest.spec.workflows[0].flow
    assert flow.kind == "http"
    assert flow.slot == "webhook_result"
    assert flow.optional is False

    compiled = compile_workflow_package_manifest(result.manifest)
    compiled_plan = cast(dict[str, Any], compiled["compiledPlan"])
    workflow = cast(list[dict[str, Any]], compiled_plan["workflows"])[0]
    operation = cast(list[dict[str, Any]], workflow["steps"])[0]["operations"][0]
    request = cast(dict[str, Any], operation["request"])

    assert operation["operationKind"] == "http"
    assert operation["method"] == "POST"
    assert request["headers"]["Authorization"] == {
        "from": "secret",
        "key": "slack_webhook_token",
    }
    assert request["body"]["token"] == {"from": "secret", "key": "body_token"}
    assert "slack-secret-value" not in str(compiled)


def test_http_node_rejects_secret_refs_outside_http_request_fields() -> None:
    data = _http_node_manifest_data()
    data["metadata"]["description"] = "${{ secrets.not_allowed_here }}"

    result = parse_workflow_package_manifest(dump_manifest(data))

    assert result.manifest is None
    assert any(
        diagnostic.path == "metadata.description"
        and "only supported in HTTP request fields" in diagnostic.message
        for diagnostic in result.diagnostics
    )


def test_http_node_rejects_duplicate_id_and_slot() -> None:
    source = dump_manifest(
        base_manifest_data(
            package_key="duplicate_http_callbacks",
            package_name="Duplicate HTTP Callback Package",
            package_description=None,
            input_schema={"type": "object"},
            output_schema_key="webhook_response",
            output_schemas=[
                {
                    "key": "webhook_response",
                    "name": "Webhook Response",
                    "jsonSchema": {"type": "object"},
                }
            ],
            agents=[],
            workflows=[
                {
                    "key": "notify",
                    "name": "Notify",
                    "inputSchema": {"type": "object"},
                    "flow": {
                        "kind": "sequence",
                        "id": "notify_sequence",
                        "nodes": [
                            {
                                "kind": "http",
                                "id": "notify_slack",
                                "slot": "webhook_result",
                                "method": "POST",
                                "url": "${{ inputs.webhookUrl }}",
                                "response": {"outputSchema": "webhook_response"},
                            },
                            {
                                "kind": "http",
                                "id": "notify_slack",
                                "slot": "webhook_result",
                                "method": "POST",
                                "url": "${{ inputs.webhookUrl }}",
                                "response": {"outputSchema": "webhook_response"},
                            },
                        ],
                    },
                    "output": {"from": "${{ nodes.notify_slack.outputs.webhook_result }}"},
                }
            ],
        )
    )

    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert any("Duplicate node id: notify_slack" in item.message for item in result.diagnostics)
    assert any(
        "Duplicate output slot name within the same sequence" in item.message
        for item in result.diagnostics
    )
