# pyright: reportExplicitAny=false, reportPrivateUsage=false
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from typing import Any, cast

from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from tests.test_workflow_package_manifest_http_node import http_node_package_source
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def _compiled_plan(source: str) -> dict[str, Any]:
    compiled = compile_workflow_package_manifest(source)
    return deepcopy(cast(dict[str, Any], compiled["compiledPlan"]))


def _first_workflow(compiled_plan: dict[str, Any]) -> dict[str, Any]:
    workflows = cast(list[dict[str, Any]], compiled_plan["workflows"])
    return workflows[0]


def test_http_node_package_execution_plan_builds_dedicated_operation() -> None:
    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        _compiled_plan(http_node_package_source()),
        "notify",
    )

    assert plan.aggregate_budget_usd == Decimal("0")
    assert plan.final_output.step_index == 1
    assert plan.final_output.slot == "webhook_result"
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.agents == ()
    assert len(step.operations) == 1

    operation = step.operations[0]
    assert operation.operation_kind == "http"
    assert operation.operation_key == "notify_slack"
    assert operation.slot == "webhook_result"
    assert operation.method == "POST"
    assert operation.timeout_seconds == 10
    assert operation.output_schema_id == 1
    assert operation.output_schema_version == 1
    assert operation.optional is False

    request = operation.request
    headers = cast(dict[str, Any], request["headers"])
    body = cast(dict[str, Any], request["body"])
    assert headers["Authorization"] == {"from": "secret", "key": "slack_webhook_token"}
    assert body["token"] == {"from": "secret", "key": "body_token"}

    runtime_operation = operation.package_runtime_operation
    assert runtime_operation is not None
    assert runtime_operation.key == "notify_slack"
    assert runtime_operation.kind == "http"
    assert runtime_operation.output_schema.key == "webhook_response"
    assert runtime_operation.request == operation.request

    metadata = operation.graph_metadata
    assert metadata is not None
    assert metadata.node_kind == "http"
    assert metadata.node_id == "notify_slack"
    source_refs = cast(dict[str, Any], metadata.source_refs)
    assert source_refs["url"] == {"source": "inputs", "path": "webhookUrl"}
    source_headers = cast(dict[str, Any], source_refs["headers"])
    assert source_headers["Authorization"] == {
        "source": "secrets",
        "key": "slack_webhook_token",
    }

    assert plan.package_workflow is not None
    package_step = plan.package_workflow.steps[0]
    assert package_step.agents == ()
    assert package_step.operations == (runtime_operation,)


def test_http_node_execution_plan_supports_mixed_agent_operation_steps() -> None:
    compiled_plan = _compiled_plan(_valid_package_manifest_source())
    workflow = _first_workflow(compiled_plan)
    steps = cast(list[dict[str, Any]], workflow["steps"])
    first_step = steps[0]
    first_step["operations"] = [
        {
            "operationKind": "http",
            "operationKey": "notify_after_analysis",
            "slot": "webhook_result",
            "method": "POST",
            "request": {
                "url": "https://example.test/hooks",
                "headers": {},
                "query": {},
                "body": {"ticker": {"from": "input", "path": "ticker"}},
            },
            "response": {"outputSchema": "trading_decision"},
            "timeoutSeconds": 10,
            "optional": True,
        }
    ]
    graph = cast(dict[str, Any], workflow["compiledGraph"])
    graph_nodes = cast(list[dict[str, Any]], graph["nodes"])
    graph_nodes.append(
        {
            "id": "market_analysis.notify_after_analysis",
            "nodeId": "notify_after_analysis",
            "kind": "http",
            "stepIndex": 1,
            "slot": "webhook_result",
            "operationKey": "notify_after_analysis",
            "method": "POST",
            "refs": {"body": {"ticker": {"source": "inputs", "path": "ticker"}}},
            "optional": True,
        }
    )

    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        compiled_plan,
        "daily_research",
    )

    assert len(plan.steps) == 1
    mixed_step = plan.steps[0]
    assert [agent.slot for agent in mixed_step.agents] == ["decision"]
    assert [operation.slot for operation in mixed_step.operations] == ["webhook_result"]
    operation = mixed_step.operations[0]
    assert operation.operation_kind == "http"
    assert operation.optional is True
    assert operation.graph_metadata is not None
    assert operation.graph_metadata.node_kind == "http"
    assert plan.final_output.step_index == 1
    assert plan.final_output.slot == "decision"
    assert plan.package_workflow is not None
    assert len(plan.package_workflow.steps[0].agents) == 1
    assert len(plan.package_workflow.steps[0].operations) == 1


def test_existing_package_execution_plan_keeps_pure_agent_shape_backward_compat() -> None:
    compiled_plan = _compiled_plan(_valid_package_manifest_source())
    workflow = _first_workflow(compiled_plan)
    compiled_steps = cast(list[dict[str, Any]], workflow["steps"])

    assert all("operations" not in step for step in compiled_steps)

    plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        compiled_plan,
        "daily_research",
    )

    assert len(plan.steps) == 1
    assert [len(step.agents) for step in plan.steps] == [1]
    assert all(step.operations == () for step in plan.steps)
    assert plan.package_workflow is not None
    assert all(package_step.operations == () for package_step in plan.package_workflow.steps)
