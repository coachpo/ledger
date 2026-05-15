from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import cast

from app.agents import ToolCatalog, ToolCatalogValidationError, get_default_tool_catalog
from app.schemas.workflow_package_manifest import (
    WorkflowPackageAgent,
    WorkflowPackageCapabilityProfile,
    WorkflowPackageFanoutNode,
    WorkflowPackageHttpNode,
    WorkflowPackageManifest,
    WorkflowPackageManifestDiagnostic,
    WorkflowPackageManifestDiagnosticSeverity,
    WorkflowPackageMcpServer,
    WorkflowPackageNode,
    WorkflowPackageReference,
    WorkflowPackageSecretReference,
    WorkflowPackageSequenceNode,
    WorkflowPackageStepNode,
    WorkflowPackageWorkflow,
)
from app.services.workflow_package_manifest_parser import (
    locate_workflow_package_manifest_path,
    parse_workflow_package_manifest,
)

_REF_EXPR_RE = re.compile(r"^\$\{\{\s*(?P<body>[^{}]+?)\s*\}\}$")


class WorkflowPackageManifestCompilerError(ValueError):
    def __init__(self, diagnostics: list[WorkflowPackageManifestDiagnostic]) -> None:
        super().__init__("Workflow package manifest could not be compiled")
        self.diagnostics: list[WorkflowPackageManifestDiagnostic] = diagnostics


@dataclass
class _WorkflowCompileContext:
    steps: list[dict[str, object]] = field(default_factory=list)
    node_outputs: dict[str, dict[str, tuple[int, str]]] = field(default_factory=dict)
    graph_nodes: list[dict[str, object]] = field(default_factory=list)

    def create_step(self, agent: dict[str, object]) -> tuple[int, str]:
        step_index = len(self.steps) + 1
        self.steps.append({"index": step_index, "agents": [agent]})
        return step_index, str(agent["slot"])

    def create_operation(self, operation: dict[str, object]) -> tuple[int, str]:
        step_index = len(self.steps) + 1
        self.steps.append({"index": step_index, "operations": [operation]})
        return step_index, str(operation["slot"])

    def register_outputs(self, node_id: str, outputs: dict[str, tuple[int, str]]) -> None:
        self.node_outputs[node_id] = dict(outputs)


def compile_workflow_package_manifest(
    source: str | WorkflowPackageManifest,
    *,
    tool_catalog: ToolCatalog | None = None,
) -> dict[str, object]:
    manifest, source_text = _resolve_manifest(source)
    resolved_tool_catalog = tool_catalog or get_default_tool_catalog()
    diagnostics = _validate_package_refs(
        manifest,
        source_text,
        tool_catalog=resolved_tool_catalog,
    )
    if diagnostics:
        raise WorkflowPackageManifestCompilerError(diagnostics)

    package_definition = _canonical_manifest_definition(manifest)
    # Private MCP env, headers, and query values stay as ordinary manifest data.
    compiled_plan = _compile_plan(manifest, tool_catalog=resolved_tool_catalog)
    return {
        "packageDefinition": package_definition,
        "compiledPlan": compiled_plan,
        "manifestHash": _sha256_json(package_definition),
        "compiledHash": _sha256_json(compiled_plan),
        "diagnostics": [],
    }


def _resolve_manifest(
    source: str | WorkflowPackageManifest,
) -> tuple[WorkflowPackageManifest, str | None]:
    if isinstance(source, WorkflowPackageManifest):
        return source, None
    result = parse_workflow_package_manifest(source)
    if result.manifest is None or result.diagnostics:
        raise WorkflowPackageManifestCompilerError(result.diagnostics)
    return result.manifest, source


def _canonical_manifest_definition(manifest: WorkflowPackageManifest) -> dict[str, object]:
    return cast(
        dict[str, object],
        _strip_empty_private_mcp_fields(
            manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
        ),
    )


def _strip_empty_private_mcp_fields(value: object) -> object:
    if isinstance(value, dict):
        source = cast(dict[object, object], value)
        is_mcp_server = (
            "transport" in source
            and "key" in source
            and ("command" in source or "url" in source or "toolKeys" in source)
        )
        sanitized: dict[str, object] = {}
        for raw_key, item in source.items():
            if not isinstance(raw_key, str):
                continue
            stripped_item = _strip_empty_private_mcp_fields(item)
            if is_mcp_server and raw_key in {"args", "env", "headers", "query"}:
                if raw_key == "args" and stripped_item == []:
                    continue
                if raw_key != "args" and stripped_item == {}:
                    continue
            sanitized[raw_key] = stripped_item
        return sanitized
    if isinstance(value, list):
        return [_strip_empty_private_mcp_fields(item) for item in cast(list[object], value)]
    return value


def _compile_plan(
    manifest: WorkflowPackageManifest,
    *,
    tool_catalog: ToolCatalog,
) -> dict[str, object]:
    return {
        "packageKey": manifest.metadata.key,
        "inputs": manifest.spec.inputs,
        "capabilityProfiles": [
            {
                "key": profile.key,
                "name": profile.name,
                "description": profile.description,
                "toolKeys": _resolved_profile_tool_keys(profile, tool_catalog),
            }
            for profile in sorted(manifest.spec.capability_profiles, key=lambda item: item.key)
        ],
        "outputSchemas": [
            {
                "key": schema.key,
                "name": schema.name,
                "description": schema.description,
                "jsonSchema": schema.json_schema,
            }
            for schema in sorted(manifest.spec.output_schemas, key=lambda item: item.key)
        ],
        "mcpServers": [
            _compile_mcp_server(server)
            for server in sorted(manifest.spec.mcp_servers, key=lambda item: item.key)
        ],
        "agents": [
            _compile_agent(agent)
            for agent in sorted(manifest.spec.agents, key=lambda item: item.key)
        ],
        "workflows": [
            _compile_workflow(workflow)
            for workflow in sorted(manifest.spec.workflows, key=lambda item: item.key)
        ],
    }


def _resolved_profile_tool_keys(
    profile: WorkflowPackageCapabilityProfile,
    tool_catalog: ToolCatalog,
) -> list[str]:
    return sorted(tool.key for tool in tool_catalog.resolve_tool_keys(profile.tool_keys))


def _compile_mcp_server(server: WorkflowPackageMcpServer) -> dict[str, object]:
    payload = cast(
        dict[str, object], server.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    if "toolKeys" in payload:
        payload["toolKeys"] = sorted(cast(list[str], payload["toolKeys"]))
    return payload


def _compile_agent(agent: WorkflowPackageAgent) -> dict[str, object]:
    return {
        "key": agent.key,
        "name": agent.name,
        "description": agent.description,
        "modelConnection": agent.model_connection,
        "systemPrompt": agent.system_prompt,
        "inputSchema": agent.input_schema,
        "outputSchema": agent.output_schema,
        "capabilityProfiles": sorted(agent.capability_profiles),
        "mcpServers": sorted(agent.mcp_servers),
        "budgetUsd": agent.budget_usd,
    }


def _compile_workflow(workflow: WorkflowPackageWorkflow) -> dict[str, object]:
    context = _WorkflowCompileContext()
    _ = _compile_node(workflow.flow, context=context, graph_path=workflow.flow.id)
    return {
        "key": workflow.key,
        "name": workflow.name,
        "description": workflow.description,
        "inputSchema": workflow.input_schema,
        "steps": context.steps,
        "outputSpec": _compile_output(workflow.output.from_, context),
        "compiledGraph": {
            "apiVersion": "ledger.workflowPackage/v1",
            "rootNodeId": workflow.flow.id,
            "nodes": context.graph_nodes,
            "output": _compile_graph_ref(workflow.output.from_, context),
        },
    }


def _compile_node(
    node: WorkflowPackageNode, *, context: _WorkflowCompileContext, graph_path: str
) -> dict[str, tuple[int, str]]:
    if isinstance(node, WorkflowPackageStepNode):
        return _compile_step_node(node, context=context, graph_path=graph_path)
    if isinstance(node, WorkflowPackageHttpNode):
        return _compile_http_node(node, context=context, graph_path=graph_path)
    if isinstance(node, WorkflowPackageSequenceNode):
        sequence_outputs: dict[str, tuple[int, str]] = {}
        context.graph_nodes.append(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "sequence",
                "childNodeIds": [child.id for child in node.nodes],
            }
        )
        for child in node.nodes:
            sequence_outputs.update(
                _compile_node(child, context=context, graph_path=f"{graph_path}.{child.id}")
            )
        context.register_outputs(node.id, sequence_outputs)
        return sequence_outputs
    if isinstance(node, WorkflowPackageFanoutNode):
        fanout_outputs: dict[str, tuple[int, str]] = {}
        context.graph_nodes.append(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "fanout",
                "branchIds": [branch.id for branch in node.branches],
            }
        )
        baseline = {node_id: dict(slots) for node_id, slots in context.node_outputs.items()}
        branch_output_refs: dict[str, dict[str, tuple[int, str]]] = {}
        for branch in node.branches:
            context.node_outputs = {node_id: dict(slots) for node_id, slots in baseline.items()}
            branch_outputs = _compile_node(
                branch.node,
                context=context,
                graph_path=f"{graph_path}.{branch.id}.{branch.node.id}",
            )
            fanout_outputs.update(branch_outputs)
            if branch_outputs:
                fanout_outputs[branch.id] = next(iter(branch_outputs.values()))
            branch_output_refs.update(
                {
                    node_id: slots
                    for node_id, slots in context.node_outputs.items()
                    if node_id not in baseline
                }
            )
        context.node_outputs = {node_id: dict(slots) for node_id, slots in baseline.items()}
        context.node_outputs.update(branch_output_refs)
        context.register_outputs(node.id, fanout_outputs)
        return fanout_outputs
    context.graph_nodes.append(
        {
            "id": graph_path,
            "nodeId": node.id,
            "kind": "loop",
            "maxIterations": node.max_iterations,
            "sequenceNodeId": node.sequence.id,
        }
    )
    loop_outputs: dict[str, tuple[int, str]] = {}
    for iteration in range(1, node.max_iterations + 1):
        loop_outputs = _compile_node(
            node.sequence,
            context=context,
            graph_path=f"{graph_path}.iteration_{iteration}.{node.sequence.id}",
        )
    context.register_outputs(node.id, loop_outputs)
    return loop_outputs


def _compile_step_node(
    node: WorkflowPackageStepNode, *, context: _WorkflowCompileContext, graph_path: str
) -> dict[str, tuple[int, str]]:
    agent: dict[str, object] = {
        "agentKey": node.uses,
        "slot": node.slot,
        "wiring": {
            field_name: _compile_ref(reference, context)
            for field_name, reference in node.inputs.items()
        },
        "optional": node.optional,
    }
    step_index, slot = context.create_step(agent)
    output = {node.slot: (step_index, slot)}
    context.register_outputs(node.id, output)
    context.graph_nodes.append(
        {
            "id": graph_path,
            "nodeId": node.id,
            "kind": "step",
            "stepIndex": step_index,
            "slot": node.slot,
            "agentKey": node.uses,
            "refs": {
                field_name: _compile_graph_ref(reference, context)
                for field_name, reference in node.inputs.items()
            },
            "optional": node.optional,
        }
    )
    return output


def _compile_http_node(
    node: WorkflowPackageHttpNode, *, context: _WorkflowCompileContext, graph_path: str
) -> dict[str, tuple[int, str]]:
    request: dict[str, object] = {
        "url": _compile_http_request_value(node.url, context),
        "headers": _compile_http_request_value(node.headers, context),
        "query": _compile_http_request_value(node.query, context),
    }
    if node.body is not None:
        request["body"] = _compile_http_request_value(node.body, context)
    operation: dict[str, object] = {
        "operationKind": "http",
        "operationKey": node.id,
        "slot": node.slot,
        "method": node.method,
        "request": request,
        "response": {"outputSchema": node.response.output_schema},
        "timeoutSeconds": node.timeout_seconds,
        "optional": node.optional,
    }
    step_index, slot = context.create_operation(operation)
    output = {node.slot: (step_index, slot)}
    context.register_outputs(node.id, output)
    context.graph_nodes.append(
        {
            "id": graph_path,
            "nodeId": node.id,
            "kind": "http",
            "stepIndex": step_index,
            "slot": node.slot,
            "operationKey": node.id,
            "method": node.method,
            "refs": _compile_graph_request_refs(
                {
                    "url": node.url,
                    "headers": node.headers,
                    "query": node.query,
                    "body": node.body,
                },
                context,
            ),
            "optional": node.optional,
        }
    )
    return output


def _compile_ref(
    reference: WorkflowPackageReference, context: _WorkflowCompileContext
) -> dict[str, object]:
    if reference.source == "inputs":
        return {"from": "input", "path": str(reference.path)}
    step_index, slot = context.node_outputs[str(reference.node_id)][str(reference.slot)]
    payload: dict[str, object] = {"from": "step", "stepIndex": step_index, "slot": slot}
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_http_request_value(value: object, context: _WorkflowCompileContext) -> object:
    if isinstance(value, dict):
        source = cast(dict[object, object], value)
        return {
            str(key): _compile_http_request_value(item, context) for key, item in source.items()
        }
    if isinstance(value, list):
        return [_compile_http_request_value(item, context) for item in cast(list[object], value)]
    if not isinstance(value, str):
        return value
    expression = value.strip()
    match = _REF_EXPR_RE.fullmatch(expression)
    if match is None:
        return value
    body = match.group("body").strip()
    if body.startswith("secrets."):
        secret_ref = WorkflowPackageSecretReference.model_validate(expression)
        return {"from": "secret", "key": secret_ref.key}
    return _compile_ref(WorkflowPackageReference.model_validate(expression), context)


def _compile_graph_request_refs(value: object, context: _WorkflowCompileContext) -> object:
    if isinstance(value, dict):
        source = cast(dict[object, object], value)
        compiled_mapping = {
            str(key): _compile_graph_request_refs(item, context) for key, item in source.items()
        }
        return {key: item for key, item in compiled_mapping.items() if item is not None}
    if isinstance(value, list):
        compiled_items = [
            _compile_graph_request_refs(item, context) for item in cast(list[object], value)
        ]
        return [item for item in compiled_items if item is not None]
    if not isinstance(value, str):
        return None
    expression = value.strip()
    match = _REF_EXPR_RE.fullmatch(expression)
    if match is None:
        return None
    body = match.group("body").strip()
    if body.startswith("secrets."):
        secret_ref = WorkflowPackageSecretReference.model_validate(expression)
        return {"source": "secrets", "key": secret_ref.key}
    return _compile_graph_ref(WorkflowPackageReference.model_validate(expression), context)


def _compile_graph_ref(
    reference: WorkflowPackageReference, context: _WorkflowCompileContext
) -> dict[str, object]:
    if reference.source == "inputs":
        return {"source": "inputs", "path": str(reference.path)}
    step_index, slot = context.node_outputs[str(reference.node_id)][str(reference.slot)]
    payload: dict[str, object] = {
        "source": "nodes",
        "nodeId": str(reference.node_id),
        "slot": str(reference.slot),
        "stepIndex": step_index,
        "compiledSlot": slot,
    }
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_output(
    reference: WorkflowPackageReference, context: _WorkflowCompileContext
) -> dict[str, object]:
    step_index, slot = context.node_outputs[str(reference.node_id)][str(reference.slot)]
    payload: dict[str, object] = {"kind": "slot", "stepIndex": step_index, "slot": slot}
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _validate_package_refs(
    manifest: WorkflowPackageManifest,
    source: str | None,
    *,
    tool_catalog: ToolCatalog,
) -> list[WorkflowPackageManifestDiagnostic]:
    diagnostics: list[WorkflowPackageManifestDiagnostic] = []
    output_schemas = {schema.key for schema in manifest.spec.output_schemas}
    capability_profiles = {profile.key for profile in manifest.spec.capability_profiles}
    mcp_servers = {server.key for server in manifest.spec.mcp_servers}
    agents = {agent.key for agent in manifest.spec.agents}

    for profile in manifest.spec.capability_profiles:
        diagnostics.extend(_validate_capability_profile_tools(profile, tool_catalog, source))

    for index, agent in enumerate(manifest.spec.agents):
        if agent.output_schema not in output_schemas:
            diagnostics.append(
                _diagnostic(
                    f"Package output schema {agent.output_schema!r} was not found",
                    path=f"spec.agents[{index}].outputSchema",
                    source=source,
                )
            )
        for ref_index, ref in enumerate(agent.capability_profiles):
            if ref not in capability_profiles:
                diagnostics.append(
                    _diagnostic(
                        f"Package capability profile {ref!r} was not found",
                        path=f"spec.agents[{index}].capabilityProfiles[{ref_index}]",
                        source=source,
                    )
                )
        for ref_index, ref in enumerate(agent.mcp_servers):
            if ref not in mcp_servers:
                diagnostics.append(
                    _diagnostic(
                        f"Package MCP server {ref!r} was not found",
                        path=f"spec.agents[{index}].mcpServers[{ref_index}]",
                        source=source,
                    )
                )

    for workflow_index, workflow in enumerate(manifest.spec.workflows):
        _validate_workflow_refs(
            workflow.flow,
            agents,
            output_schemas,
            path=f"spec.workflows[{workflow_index}].flow",
            source=source,
            diagnostics=diagnostics,
        )
    return diagnostics


def _validate_capability_profile_tools(
    profile: WorkflowPackageCapabilityProfile,
    tool_catalog: ToolCatalog,
    source: str | None,
) -> list[WorkflowPackageManifestDiagnostic]:
    try:
        _ = tool_catalog.resolve_tool_keys(profile.tool_keys)
    except ToolCatalogValidationError as exc:
        return [
            _diagnostic(
                str(detail.get("issue", "Invalid server-declared tool key")),
                path=_profile_tool_key_path(profile.key, str(detail.get("field", "toolKeys"))),
                source=source,
            )
            for detail in exc.details
        ]
    return []


def _profile_tool_key_path(profile_key: str, field: str) -> str:
    if field.startswith("toolKeys."):
        index = field.removeprefix("toolKeys.")
        return f"spec.capabilityProfiles.{profile_key}.toolKeys[{index}]"
    return f"spec.capabilityProfiles.{profile_key}.toolKeys"


def _validate_workflow_refs(
    node: WorkflowPackageNode,
    agents: set[str],
    output_schemas: set[str],
    *,
    path: str,
    source: str | None,
    diagnostics: list[WorkflowPackageManifestDiagnostic],
) -> None:
    if isinstance(node, WorkflowPackageStepNode):
        if node.uses not in agents:
            diagnostics.append(
                _diagnostic(
                    f"Package agent {node.uses!r} was not found", path=f"{path}.uses", source=source
                )
            )
        return
    if isinstance(node, WorkflowPackageHttpNode):
        if node.response.output_schema not in output_schemas:
            diagnostics.append(
                _diagnostic(
                    f"Package output schema {node.response.output_schema!r} was not found",
                    path=f"{path}.response.outputSchema",
                    source=source,
                )
            )
        return
    if isinstance(node, WorkflowPackageSequenceNode):
        for index, child in enumerate(node.nodes):
            _validate_workflow_refs(
                child,
                agents,
                output_schemas,
                path=f"{path}.nodes[{index}]",
                source=source,
                diagnostics=diagnostics,
            )
        return
    if isinstance(node, WorkflowPackageFanoutNode):
        for index, branch in enumerate(node.branches):
            _validate_workflow_refs(
                branch.node,
                agents,
                output_schemas,
                path=f"{path}.branches[{index}].node",
                source=source,
                diagnostics=diagnostics,
            )
        return
    _validate_workflow_refs(
        node.sequence,
        agents,
        output_schemas,
        path=f"{path}.sequence",
        source=source,
        diagnostics=diagnostics,
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _diagnostic(
    message: str, *, path: str, source: str | None
) -> WorkflowPackageManifestDiagnostic:
    line, column = (
        locate_workflow_package_manifest_path(source, path) if source is not None else (None, None)
    )
    return WorkflowPackageManifestDiagnostic(
        severity=WorkflowPackageManifestDiagnosticSeverity.ERROR,
        message=message,
        path=path,
        line=line,
        column=column,
    )


__all__ = [
    "WorkflowPackageManifestCompilerError",
    "compile_workflow_package_manifest",
]
