# pyright: reportExplicitAny=false, reportAny=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnannotatedClassAttribute=false
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from app.services.execution_ownership import PackageExecutionOwnership
from app.services.execution_plan import (
    ExecutionPlan,
    ExecutionPlanAgent,
    ExecutionPlanFinalOutput,
    ExecutionPlanGraphMetadata,
    ExecutionPlanOperation,
    ExecutionPlanSource,
    ExecutionPlanSourceKind,
    ExecutionPlanStep,
    ExecutionPlanTarget,
    PackageCapabilityProfileGrant,
    PackageExecutionStep,
    PackageExecutionWorkflow,
    PackageLocalOutputSchemaSpec,
    PackagePrivateMcpConfig,
    PackageResolvedModelBinding,
    PackageRuntimeAgentSpec,
    PackageRuntimeOperationSpec,
)

_PACKAGE_TARGET_ID = 1
_PACKAGE_TARGET_VERSION = 1
_PACKAGE_OUTPUT_SCHEMA_VERSION = 1
_PACKAGE_AGENT_VERSION = 1
_SUPPORTED_GRAPH_NODE_KINDS = {"sequence", "fanout", "loop", "step", "http"}
_EXECUTABLE_GRAPH_NODE_KINDS = {"step", "http"}


@dataclass(frozen=True)
class WorkflowPackageExecutionPlanError(Exception):
    code: str
    message: str
    field: str
    issue: str
    details: tuple[dict[str, Any], ...] = dataclass_field(default_factory=tuple)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    @classmethod
    def validation(
        cls, *, field: str, issue: str, message: str
    ) -> WorkflowPackageExecutionPlanError:
        return cls(
            code="workflow_package_execution_plan_invalid",
            message=message,
            field=field,
            issue=issue,
            details=({"field": field, "issue": issue},),
        )


class PackageExecutionPlanBuilder:
    def __init__(
        self,
        compiled_plan: Mapping[str, Any],
        *,
        model_bindings: Mapping[str, PackageResolvedModelBinding | Any] | None = None,
        package_version: int = _PACKAGE_TARGET_VERSION,
        ownership: PackageExecutionOwnership | None = None,
    ) -> None:
        self.compiled_plan = dict(compiled_plan)
        self.package_version = package_version
        self.ownership = ownership
        self.model_bindings = {
            key: self._coerce_model_binding(key, binding)
            for key, binding in (model_bindings or {}).items()
        }
        self.package_key = str(self.compiled_plan.get("packageKey") or "workflow_package")
        self.output_schemas = self._build_output_schema_specs()
        self.capability_profiles = self._build_capability_profile_grants()
        self.mcp_servers = self._build_mcp_configs()
        self.runtime_agents = self._build_runtime_agent_specs()
        self.workflows = self._build_workflow_index()

    def build_workflow_plan(self, workflow_key: str) -> ExecutionPlan:
        workflow = self.workflows.get(workflow_key)
        if workflow is None:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.workflows.{workflow_key}",
                issue="missing_entry_workflow",
                message=f"Package workflow {workflow_key!r} was not found",
            )
        return self._build_plan_for_workflow(workflow)

    @classmethod
    def build_from_compiled_plan(
        cls,
        compiled_plan: Mapping[str, Any],
        workflow_key: str,
        *,
        model_bindings: Mapping[str, PackageResolvedModelBinding | Any] | None = None,
        package_version: int = _PACKAGE_TARGET_VERSION,
        ownership: PackageExecutionOwnership | None = None,
    ) -> ExecutionPlan:
        return cls(
            compiled_plan,
            model_bindings=model_bindings,
            package_version=package_version,
            ownership=ownership,
        ).build_workflow_plan(workflow_key)

    def _build_plan_for_workflow(self, workflow: dict[str, Any]) -> ExecutionPlan:
        workflow_key = str(workflow["key"])
        raw_steps = self._require_list(
            workflow.get("steps"),
            field=f"spec.workflows.{workflow_key}.steps",
            issue="missing_steps",
        )
        output_spec = self._require_mapping(
            workflow.get("outputSpec"),
            field=f"spec.workflows.{workflow_key}.outputSpec",
            issue="missing_output_spec",
        )
        compiled_graph = self._optional_mapping(workflow.get("compiledGraph"))
        self._validate_graph(workflow_key, raw_steps, output_spec, compiled_graph)
        graph_metadata_by_step_slot = self._build_step_slot_graph_metadata(compiled_graph)

        steps: list[ExecutionPlanStep] = []
        package_steps: list[PackageExecutionStep] = []
        for raw_step in raw_steps:
            step = self._build_step(
                workflow_key,
                self._require_mapping(raw_step, field="step", issue="invalid_step"),
                graph_metadata_by_step_slot=graph_metadata_by_step_slot,
            )
            steps.append(step)
            package_agents = tuple(
                agent.package_runtime_agent
                for agent in step.agents
                if agent.package_runtime_agent is not None
            )
            package_operations = tuple(
                operation.package_runtime_operation
                for operation in step.operations
                if operation.package_runtime_operation is not None
            )
            package_steps.append(
                PackageExecutionStep(
                    index=step.index,
                    agents=package_agents,
                    operations=package_operations,
                    graph_metadata=step.graph_metadata,
                )
            )
            steps[-1] = ExecutionPlanStep(
                index=step.index,
                agents=step.agents,
                operations=step.operations,
                graph_metadata=step.graph_metadata,
                package_step=package_steps[-1],
            )

        final_output = self._build_final_output_selector(output_spec)
        package_workflow = PackageExecutionWorkflow(
            package_key=self.package_key,
            key=workflow_key,
            name=str(workflow.get("name") or workflow_key),
            description=str(workflow.get("description") or ""),
            input_schema=deepcopy(cast(dict[str, Any], workflow.get("inputSchema") or {})),
            steps=tuple(package_steps),
            final_output=final_output,
            compiled_graph=deepcopy(compiled_graph),
        )
        target_id = self.ownership.package_id if self.ownership is not None else _PACKAGE_TARGET_ID
        target_key = self.ownership.package_key if self.ownership is not None else workflow_key
        target_version = (
            self.ownership.package_version if self.ownership is not None else self.package_version
        )
        return ExecutionPlan(
            target=ExecutionPlanTarget(
                kind="workflow_package",
                id=target_id,
                key=target_key,
                version=target_version,
            ),
            input_schema=deepcopy(cast(dict[str, Any], workflow.get("inputSchema") or {})),
            aggregate_budget_usd=sum(
                (
                    agent.package_runtime_agent.budget_usd
                    for step in steps
                    for agent in step.agents
                    if agent.package_runtime_agent is not None
                ),
                Decimal("0"),
            ),
            steps=tuple(steps),
            final_output=final_output,
            package_workflow=package_workflow,
            package_ownership=self.ownership,
        )

    def _build_runtime_agent_specs(self) -> dict[str, PackageRuntimeAgentSpec]:
        agents: dict[str, PackageRuntimeAgentSpec] = {}
        for index, raw_agent in enumerate(self._iter_section("agents"), start=1):
            agent_key = str(raw_agent.get("key") or "")
            schema_key = str(raw_agent.get("outputSchema") or "")
            output_schema = self.output_schemas.get(schema_key)
            if output_schema is None:
                raise WorkflowPackageExecutionPlanError.validation(
                    field=f"spec.agents.{agent_key}.outputSchema",
                    issue="missing_local_output_schema",
                    message=(
                        f"Package agent {agent_key!r} references missing "
                        f"output schema {schema_key!r}"
                    ),
                )
            capability_profiles = tuple(
                self._resolve_capability_profile(agent_key, profile_key, profile_index)
                for profile_index, profile_key in enumerate(
                    cast(list[Any], raw_agent.get("capabilityProfiles") or [])
                )
            )
            mcp_servers = tuple(
                self._resolve_mcp_server(agent_key, server_key, server_index)
                for server_index, server_key in enumerate(
                    cast(list[Any], raw_agent.get("mcpServers") or [])
                )
            )
            model_key = str(raw_agent.get("modelConnection") or "")
            agents[agent_key] = PackageRuntimeAgentSpec(
                local_id=index,
                key=agent_key,
                name=str(raw_agent.get("name") or agent_key),
                description=str(raw_agent.get("description") or ""),
                model_binding=self.model_bindings.get(model_key),
                system_prompt=str(raw_agent.get("systemPrompt") or ""),
                input_schema=deepcopy(cast(dict[str, Any], raw_agent.get("inputSchema") or {})),
                output_schema=output_schema,
                capability_profiles=capability_profiles,
                mcp_servers=mcp_servers,
                budget_usd=self._parse_budget(raw_agent.get("budgetUsd"), agent_key=agent_key),
            )
        return agents

    def _build_output_schema_specs(self) -> dict[str, PackageLocalOutputSchemaSpec]:
        return {
            str(raw_schema.get("key")): PackageLocalOutputSchemaSpec(
                local_id=index,
                key=str(raw_schema.get("key")),
                name=str(raw_schema.get("name") or raw_schema.get("key")),
                description=str(raw_schema.get("description") or ""),
                json_schema=deepcopy(cast(dict[str, Any], raw_schema.get("jsonSchema") or {})),
            )
            for index, raw_schema in enumerate(self._iter_section("outputSchemas"), start=1)
        }

    def _build_capability_profile_grants(self) -> dict[str, PackageCapabilityProfileGrant]:
        return {
            str(raw_profile.get("key")): PackageCapabilityProfileGrant(
                key=str(raw_profile.get("key")),
                name=str(raw_profile.get("name") or raw_profile.get("key")),
                description=str(raw_profile.get("description") or ""),
                tool_keys=tuple(str(key) for key in raw_profile.get("toolKeys") or []),
            )
            for raw_profile in self._iter_section("capabilityProfiles")
        }

    def _build_mcp_configs(self) -> dict[str, PackagePrivateMcpConfig]:
        return {
            str(raw_server.get("key")): PackagePrivateMcpConfig(
                key=str(raw_server.get("key")),
                name=str(raw_server.get("name") or raw_server.get("key")),
                description=str(raw_server.get("description") or ""),
                transport=str(raw_server.get("transport") or ""),
                command=None if raw_server.get("command") is None else str(raw_server["command"]),
                args=tuple(str(arg) for arg in raw_server.get("args") or []),
                url=None if raw_server.get("url") is None else str(raw_server["url"]),
                env=deepcopy(cast(dict[str, Any], raw_server.get("env") or {})),
                headers=deepcopy(cast(dict[str, Any], raw_server.get("headers") or {})),
                query=deepcopy(cast(dict[str, Any], raw_server.get("query") or {})),
                tool_keys=tuple(
                    normalized_key
                    for key in raw_server.get("toolKeys") or []
                    if (normalized_key := str(key).strip().lower())
                ),
                tool_descriptors=tuple(
                    deepcopy(cast(dict[str, Any], descriptor))
                    for descriptor in raw_server.get("toolDescriptors") or []
                    if isinstance(descriptor, dict)
                ),
            )
            for raw_server in self._iter_section("mcpServers")
        }

    def _build_workflow_index(self) -> dict[str, dict[str, Any]]:
        return {str(workflow.get("key")): workflow for workflow in self._iter_section("workflows")}

    def _build_step(
        self,
        workflow_key: str,
        raw_step: dict[str, Any],
        *,
        graph_metadata_by_step_slot: dict[tuple[int, str], ExecutionPlanGraphMetadata],
    ) -> ExecutionPlanStep:
        step_index = int(raw_step["index"])
        agents = tuple(
            self._build_step_agent(
                workflow_key,
                step_index,
                agent_index,
                self._require_mapping(raw_agent, field="agent", issue="invalid_agent"),
                graph_metadata_by_step_slot=graph_metadata_by_step_slot,
            )
            for agent_index, raw_agent in enumerate(cast(list[Any], raw_step.get("agents") or []))
        )
        operations = tuple(
            self._build_step_operation(
                workflow_key,
                step_index,
                operation_index,
                self._require_mapping(
                    raw_operation,
                    field="operation",
                    issue="invalid_operation",
                ),
                graph_metadata_by_step_slot=graph_metadata_by_step_slot,
            )
            for operation_index, raw_operation in enumerate(
                cast(list[Any], raw_step.get("operations") or [])
            )
        )
        return ExecutionPlanStep(
            index=step_index,
            agents=agents,
            operations=operations,
            graph_metadata=self._build_step_graph_metadata(agents, operations),
        )

    def _build_step_agent(
        self,
        workflow_key: str,
        step_index: int,
        agent_index: int,
        raw_agent: dict[str, Any],
        *,
        graph_metadata_by_step_slot: dict[tuple[int, str], ExecutionPlanGraphMetadata],
    ) -> ExecutionPlanAgent:
        agent_key = str(raw_agent.get("agentKey") or "")
        runtime_agent = self.runtime_agents.get(agent_key)
        if runtime_agent is None:
            raise WorkflowPackageExecutionPlanError.validation(
                field=(
                    f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                    f".agents[{agent_index}].agentRef"
                ),
                issue="missing_local_agent",
                message=(
                    f"Package workflow {workflow_key!r} references missing "
                    f"local agent {agent_key!r}"
                ),
            )
        slot = str(raw_agent["slot"])
        return ExecutionPlanAgent(
            slot=slot,
            agent_id=runtime_agent.local_id,
            agent_key=runtime_agent.key,
            agent_version=_PACKAGE_AGENT_VERSION,
            output_schema_id=runtime_agent.output_schema.local_id,
            output_schema_version=_PACKAGE_OUTPUT_SCHEMA_VERSION,
            wiring=self._build_wiring(raw_agent.get("wiring") or {}),
            optional=bool(raw_agent.get("optional", False)),
            graph_metadata=graph_metadata_by_step_slot.get((step_index, slot)),
            package_runtime_agent=runtime_agent,
        )

    def _build_step_operation(
        self,
        workflow_key: str,
        step_index: int,
        operation_index: int,
        raw_operation: dict[str, Any],
        *,
        graph_metadata_by_step_slot: dict[tuple[int, str], ExecutionPlanGraphMetadata],
    ) -> ExecutionPlanOperation:
        field_base = (
            f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
            f".operations[{operation_index}]"
        )
        operation_kind = str(raw_operation.get("operationKind") or "")
        if operation_kind != "http":
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"{field_base}.operationKind",
                issue="unsupported_operation_kind",
                message=f"Package workflow {workflow_key!r} has an unsupported operation",
            )
        operation_key = str(raw_operation.get("operationKey") or "")
        response = self._require_mapping(
            raw_operation.get("response"),
            field=f"{field_base}.response",
            issue="missing_operation_response",
        )
        schema_key = str(response.get("outputSchema") or "")
        output_schema = self.output_schemas.get(schema_key)
        if output_schema is None:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"{field_base}.response.outputSchema",
                issue="missing_local_output_schema",
                message=(
                    f"Package operation {operation_key!r} references missing "
                    f"output schema {schema_key!r}"
                ),
            )
        request = self._require_mapping(
            raw_operation.get("request"),
            field=f"{field_base}.request",
            issue="missing_operation_request",
        )
        slot = str(raw_operation["slot"])
        runtime_operation = PackageRuntimeOperationSpec(
            key=operation_key,
            kind="http",
            slot=slot,
            method=str(raw_operation.get("method") or ""),
            request=deepcopy(request),
            output_schema=output_schema,
            timeout_seconds=int(raw_operation.get("timeoutSeconds") or 30),
            optional=bool(raw_operation.get("optional", False)),
        )
        return ExecutionPlanOperation(
            slot=slot,
            operation_key=runtime_operation.key,
            operation_kind=runtime_operation.kind,
            output_schema_id=output_schema.local_id,
            output_schema_version=_PACKAGE_OUTPUT_SCHEMA_VERSION,
            request=deepcopy(request),
            method=runtime_operation.method,
            timeout_seconds=runtime_operation.timeout_seconds,
            optional=runtime_operation.optional,
            graph_metadata=graph_metadata_by_step_slot.get((step_index, slot)),
            package_runtime_operation=runtime_operation,
        )

    def _resolve_capability_profile(
        self, agent_key: str, profile_key: object, profile_index: int
    ) -> PackageCapabilityProfileGrant:
        key = str(profile_key)
        profile = self.capability_profiles.get(key)
        if profile is None:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.agents.{agent_key}.capabilityProfiles[{profile_index}]",
                issue="unknown_capability_profile",
                message=(
                    f"Package agent {agent_key!r} references missing capability profile {key!r}"
                ),
            )
        return profile

    def _resolve_mcp_server(
        self, agent_key: str, server_key: object, server_index: int
    ) -> PackagePrivateMcpConfig:
        key = str(server_key)
        server = self.mcp_servers.get(key)
        if server is None:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.agents.{agent_key}.mcpServers[{server_index}]",
                issue="unknown_mcp_config",
                message=f"Package agent {agent_key!r} references missing MCP config {key!r}",
            )
        return server

    def _validate_graph(
        self,
        workflow_key: str,
        raw_steps: list[Any],
        output_spec: dict[str, Any],
        compiled_graph: dict[str, Any] | None,
    ) -> None:
        known_step_slots = self._known_step_slots(raw_steps)
        graph_executable_slots: set[tuple[int, str]] = set()
        if compiled_graph is not None:
            for index, node in enumerate(cast(list[Any], compiled_graph.get("nodes") or [])):
                if not isinstance(node, dict):
                    raise self._graph_error(workflow_key, index, "node", "unsupported_graph_edge")
                kind = str(node.get("kind") or "")
                if kind not in _SUPPORTED_GRAPH_NODE_KINDS:
                    raise self._graph_error(workflow_key, index, "kind", "unsupported_graph_edge")
                if kind in _EXECUTABLE_GRAPH_NODE_KINDS:
                    slot_key = (int(node["stepIndex"]), str(node["slot"]))
                    graph_executable_slots.add(slot_key)
                    if slot_key not in known_step_slots:
                        raise self._graph_error(
                            workflow_key, index, "stepIndex", "unreachable_node"
                        )
        self._validate_wiring_acyclic(workflow_key, raw_steps, known_step_slots)
        final_key = (int(output_spec["stepIndex"]), str(output_spec["slot"]))
        if final_key not in known_step_slots:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.workflows.{workflow_key}.output.from",
                issue="unreachable_node",
                message="Package workflow output references an unreachable step slot",
            )
        if (
            compiled_graph is not None
            and graph_executable_slots
            and graph_executable_slots != known_step_slots
        ):
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.workflows.{workflow_key}.compiledGraph.nodes",
                issue="unreachable_node",
                message="Package workflow graph does not cover the compiled workflow steps",
            )

    def _validate_wiring_acyclic(
        self,
        workflow_key: str,
        raw_steps: list[Any],
        known_step_slots: set[tuple[int, str]],
    ) -> None:
        for raw_step in raw_steps:
            step = self._require_mapping(raw_step, field="step", issue="invalid_step")
            step_index = int(step["index"])
            for agent_index, raw_agent in enumerate(cast(list[Any], step.get("agents") or [])):
                agent = self._require_mapping(raw_agent, field="agent", issue="invalid_agent")
                for target_name, raw_source in cast(
                    dict[str, Any], agent.get("wiring") or {}
                ).items():
                    source = self._require_mapping(
                        raw_source,
                        field="source",
                        issue="invalid_source",
                    )
                    if str(source.get("from") or source.get("source") or "") != "step":
                        continue
                    self._validate_step_source(
                        workflow_key=workflow_key,
                        step_index=step_index,
                        field=(
                            f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                            f".agents[{agent_index}].with.{target_name}"
                        ),
                        source=source,
                        known_step_slots=known_step_slots,
                    )
            for operation_index, raw_operation in enumerate(
                cast(list[Any], step.get("operations") or [])
            ):
                operation = self._require_mapping(
                    raw_operation,
                    field="operation",
                    issue="invalid_operation",
                )
                request = operation.get("request") or {}
                for source_path, source in self._iter_step_sources(request):
                    self._validate_step_source(
                        workflow_key=workflow_key,
                        step_index=step_index,
                        field=(
                            f"spec.workflows.{workflow_key}.graph.steps[{step_index - 1}]"
                            f".operations[{operation_index}].request{source_path}"
                        ),
                        source=source,
                        known_step_slots=known_step_slots,
                    )

    @staticmethod
    def _validate_step_source(
        *,
        workflow_key: str,
        step_index: int,
        field: str,
        source: dict[str, Any],
        known_step_slots: set[tuple[int, str]],
    ) -> None:
        source_key = (int(source["stepIndex"]), str(source["slot"]))
        if source_key not in known_step_slots:
            raise WorkflowPackageExecutionPlanError.validation(
                field=field,
                issue="unreachable_node",
                message="Package workflow wiring references an unreachable step slot",
            )
        if source_key[0] >= step_index:
            raise WorkflowPackageExecutionPlanError.validation(
                field=field,
                issue="cycle",
                message=f"Package workflow {workflow_key!r} cannot reference a later step",
            )

    @staticmethod
    def _iter_step_sources(
        value: object,
        path: str = "",
    ) -> list[tuple[str, dict[str, Any]]]:
        if isinstance(value, dict):
            source = cast(dict[str, Any], value)
            if str(source.get("from") or source.get("source") or "") == "step":
                return [(path, source)]
            step_sources: list[tuple[str, dict[str, Any]]] = []
            for key, item in source.items():
                step_sources.extend(
                    PackageExecutionPlanBuilder._iter_step_sources(
                        item,
                        f"{path}.{key}",
                    )
                )
            return step_sources
        if isinstance(value, list):
            step_sources = []
            for index, item in enumerate(value):
                step_sources.extend(
                    PackageExecutionPlanBuilder._iter_step_sources(
                        item,
                        f"{path}[{index}]",
                    )
                )
            return step_sources
        return []

    @staticmethod
    def _known_step_slots(raw_steps: list[Any]) -> set[tuple[int, str]]:
        known: set[tuple[int, str]] = set()
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                continue
            for raw_agent in raw_step.get("agents") or []:
                if isinstance(raw_agent, dict):
                    known.add((int(raw_step["index"]), str(raw_agent["slot"])))
            for raw_operation in raw_step.get("operations") or []:
                if isinstance(raw_operation, dict):
                    known.add((int(raw_step["index"]), str(raw_operation["slot"])))
        return known

    @staticmethod
    def _graph_error(
        workflow_key: str, node_index: int, field_name: str, issue: str
    ) -> WorkflowPackageExecutionPlanError:
        return WorkflowPackageExecutionPlanError.validation(
            field=f"spec.workflows.{workflow_key}.compiledGraph.nodes[{node_index}].{field_name}",
            issue=issue,
            message=f"Package workflow {workflow_key!r} has an invalid compiled graph",
        )

    def _build_step_slot_graph_metadata(
        self,
        compiled_graph: dict[str, Any] | None,
    ) -> dict[tuple[int, str], ExecutionPlanGraphMetadata]:
        if compiled_graph is None:
            return {}
        nodes = [node for node in compiled_graph.get("nodes") or [] if isinstance(node, dict)]
        fanout_nodes = [node for node in nodes if node.get("kind") == "fanout"]
        loop_nodes = [node for node in nodes if node.get("kind") == "loop"]
        metadata: dict[tuple[int, str], ExecutionPlanGraphMetadata] = {}
        for node in nodes:
            node_kind = str(node.get("kind") or "")
            if node_kind not in _EXECUTABLE_GRAPH_NODE_KINDS:
                continue
            step_index = int(node["stepIndex"])
            slot = str(node["slot"])
            branch_id = self._resolve_branch_id(node, fanout_nodes)
            loop_id, loop_iteration = self._resolve_loop_metadata(node, loop_nodes)
            metadata[(step_index, slot)] = ExecutionPlanGraphMetadata(
                node_id=None if node.get("nodeId") is None else str(node["nodeId"]),
                node_kind=node_kind,
                graph_path=None if node.get("id") is None else str(node["id"]),
                fanout_id=self._resolve_fanout_id(node, fanout_nodes, branch_id),
                branch_id=branch_id,
                loop_id=loop_id,
                loop_iteration=loop_iteration,
                source_refs=(
                    deepcopy(cast(dict[str, Any], node.get("refs")))
                    if isinstance(node.get("refs"), dict)
                    else None
                ),
            )
        return metadata

    @staticmethod
    def _resolve_branch_id(
        step_node: dict[Any, Any], fanout_nodes: list[dict[Any, Any]]
    ) -> str | None:
        if step_node.get("branchId") is not None:
            return str(step_node["branchId"])
        graph_path = str(step_node.get("id") or "")
        for fanout in sorted(
            fanout_nodes, key=lambda item: len(str(item.get("id") or "")), reverse=True
        ):
            fanout_path = str(fanout.get("id") or "")
            if not graph_path.startswith(f"{fanout_path}."):
                continue
            remainder = graph_path.removeprefix(f"{fanout_path}.")
            branch_id = remainder.split(".", 1)[0]
            if branch_id in set(str(item) for item in fanout.get("branchIds") or []):
                return branch_id
        return None

    @staticmethod
    def _resolve_fanout_id(
        step_node: dict[Any, Any],
        fanout_nodes: list[dict[Any, Any]],
        branch_id: str | None,
    ) -> str | None:
        graph_path = str(step_node.get("id") or "")
        if branch_id is None:
            return None
        candidates = [
            node
            for node in fanout_nodes
            if isinstance(node.get("id"), str)
            and graph_path.startswith(f"{node['id']}.")
            and branch_id in set(str(item) for item in node.get("branchIds") or [])
        ]
        if not candidates:
            return None
        fanout_node = max(candidates, key=lambda item: len(str(item["id"])))
        return None if fanout_node.get("nodeId") is None else str(fanout_node["nodeId"])

    @staticmethod
    def _resolve_loop_metadata(
        step_node: dict[Any, Any],
        loop_nodes: list[dict[Any, Any]],
    ) -> tuple[str | None, int | None]:
        if step_node.get("loopId") is not None:
            return str(step_node["loopId"]), (
                None if step_node.get("loopIteration") is None else int(step_node["loopIteration"])
            )
        graph_path = str(step_node.get("id") or "")
        for loop in sorted(
            loop_nodes, key=lambda item: len(str(item.get("id") or "")), reverse=True
        ):
            loop_path = str(loop.get("id") or "")
            marker = f"{loop_path}.iteration_"
            if marker not in graph_path:
                continue
            suffix = graph_path.split(marker, 1)[1]
            iteration_text = suffix.split(".", 1)[0]
            if iteration_text.isdecimal():
                return str(loop.get("nodeId") or loop.get("loopId") or ""), int(iteration_text)
        return None, None

    @staticmethod
    def _build_step_graph_metadata(
        agents: tuple[ExecutionPlanAgent, ...],
        operations: tuple[ExecutionPlanOperation, ...],
    ) -> ExecutionPlanGraphMetadata | None:
        item_metadata: list[tuple[str, ExecutionPlanGraphMetadata]] = []
        for agent in agents:
            if agent.graph_metadata is not None:
                item_metadata.append((agent.slot, agent.graph_metadata))
        for operation in operations:
            if operation.graph_metadata is not None:
                item_metadata.append((operation.slot, operation.graph_metadata))
        if not item_metadata:
            return None
        if len(item_metadata) == 1:
            return item_metadata[0][1]
        fanout_ids = {metadata.fanout_id for _slot, metadata in item_metadata if metadata.fanout_id}
        if len(fanout_ids) == 1:
            return ExecutionPlanGraphMetadata(
                node_kind="fanout",
                fanout_id=next(iter(fanout_ids)),
                loop_id=item_metadata[0][1].loop_id,
                loop_iteration=item_metadata[0][1].loop_iteration,
                source_refs={
                    "branches": [
                        {
                            "nodeId": metadata.node_id,
                            "branchId": metadata.branch_id,
                            "slot": slot,
                        }
                        for slot, metadata in item_metadata
                    ]
                },
            )
        return None

    @staticmethod
    def _build_final_output_selector(output_spec: dict[str, Any]) -> ExecutionPlanFinalOutput:
        return ExecutionPlanFinalOutput(
            step_index=int(output_spec["stepIndex"]),
            slot=str(output_spec["slot"]),
            path=None if output_spec.get("path") is None else str(output_spec["path"]),
        )

    @staticmethod
    def _build_wiring(raw_wiring: dict[str, Any]) -> dict[str, ExecutionPlanSource]:
        return {
            str(target_name): ExecutionPlanSource(
                source=cast(
                    ExecutionPlanSourceKind,
                    str(raw_source.get("from", raw_source.get("source", ""))),
                ),
                path=None if raw_source.get("path") is None else str(raw_source["path"]),
                step_index=(
                    None if raw_source.get("stepIndex") is None else int(raw_source["stepIndex"])
                ),
                slot=None if raw_source.get("slot") is None else str(raw_source["slot"]),
            )
            for target_name, raw_source in raw_wiring.items()
            if isinstance(raw_source, dict)
        }

    @staticmethod
    def _parse_budget(value: object, *, agent_key: str) -> Decimal:
        try:
            budget = Decimal(str(value or "0"))
        except InvalidOperation as exc:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.agents.{agent_key}.budgetUsd",
                issue="invalid_budget",
                message=f"Package agent {agent_key!r} has an invalid budget",
            ) from exc
        if not budget.is_finite() or budget < 0:
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"spec.agents.{agent_key}.budgetUsd",
                issue="invalid_budget",
                message=f"Package agent {agent_key!r} has an invalid budget",
            )
        return budget

    def _iter_section(self, section_name: str) -> list[dict[str, Any]]:
        raw_items = self.compiled_plan.get(section_name) or []
        if not isinstance(raw_items, list):
            raise WorkflowPackageExecutionPlanError.validation(
                field=f"compiledPlan.{section_name}",
                issue="invalid_section",
                message=f"Package compiledPlan.{section_name} must be an array",
            )
        return [
            self._require_mapping(
                item, field=f"compiledPlan.{section_name}", issue="invalid_section"
            )
            for item in raw_items
        ]

    @staticmethod
    def _require_mapping(value: object, *, field: str, issue: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise WorkflowPackageExecutionPlanError.validation(
                field=field,
                issue=issue,
                message=f"Package execution plan field {field!r} must be an object",
            )
        return cast(dict[str, Any], value)

    @staticmethod
    def _require_list(value: object, *, field: str, issue: str) -> list[Any]:
        if not isinstance(value, list):
            raise WorkflowPackageExecutionPlanError.validation(
                field=field,
                issue=issue,
                message=f"Package execution plan field {field!r} must be an array",
            )
        return value

    @staticmethod
    def _optional_mapping(value: object) -> dict[str, Any] | None:
        return cast(dict[str, Any], value) if isinstance(value, dict) else None

    @staticmethod
    def _coerce_model_binding(
        key: str, binding: PackageResolvedModelBinding | Any
    ) -> PackageResolvedModelBinding:
        if isinstance(binding, PackageResolvedModelBinding):
            return binding
        return PackageResolvedModelBinding(
            key=str(getattr(binding, "key", key)),
            name=str(getattr(binding, "name", key)),
            connection_kind=str(getattr(binding, "connection_kind", "provider")),
            base_url=str(getattr(binding, "base_url", "")),
            model_id=str(getattr(binding, "model_id", "")),
            reasoning_effort=cast(str | None, getattr(binding, "reasoning_effort", None)),
            api_style=str(getattr(binding, "api_style", "responses")),
            timeout_seconds=int(getattr(binding, "timeout_seconds", 60)),
            has_api_key=bool(getattr(binding, "has_api_key", False)),
        )


__all__ = ["PackageExecutionPlanBuilder", "WorkflowPackageExecutionPlanError"]
