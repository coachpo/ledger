# pyright: reportPrivateUsage=false, reportExplicitAny=false

from __future__ import annotations

from typing import Any, cast

from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def test_decompile_workflow_package_manifest_round_trips_canonical_package_json() -> None:
    compiled = compile_workflow_package_manifest(_valid_package_manifest_source())
    package_definition = cast(dict[str, Any], compiled["packageDefinition"])
    package_definition["id"] = 99
    spec = cast(dict[str, Any], package_definition["spec"])
    agent = cast(list[dict[str, Any]], spec["agents"])[0]
    agent["modelConnectionId"] = 42
    agent["secretPayload"] = {"apiKey": "sk-never-export"}

    result = decompile_workflow_package_manifest(compiled)
    parsed = parse_workflow_package_manifest(result.source)
    recompiled = compile_workflow_package_manifest(result.source)

    assert result.source.startswith(
        "apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n"
    )
    assert "modelConnection: tradingagents_primary_model" in result.source
    assert "modelConnectionId" not in result.source
    assert "secretPayload" not in result.source
    assert "apiKey" not in result.source
    assert "id: 99" not in result.source
    assert parsed.diagnostics == []
    assert parsed.manifest is not None
    compiled_plan = cast(dict[str, object], recompiled["compiledPlan"])

    assert recompiled["packageDefinition"] == result.package_definition
    assert compiled_plan["packageKey"] == "tradingagents_research"
