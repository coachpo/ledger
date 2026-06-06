# pyright: reportExplicitAny=false
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.execution_ownership import PackageExecutionOwnership

ExecutionPlanInputMode = Literal["passthrough", "wired"]
ExecutionPlanOperationKind = Literal["http"]
ExecutionPlanTargetKind = Literal["workflow_package"]
ExecutionPlanSourceKind = Literal["input", "step"]


@dataclass(frozen=True)
class ExecutionPlanTarget:
    kind: ExecutionPlanTargetKind
    id: int
    key: str
    version: int | None


@dataclass(frozen=True)
class ExecutionPlanSource:
    source: ExecutionPlanSourceKind
    path: str | None = None
    step_index: int | None = None
    slot: str | None = None


@dataclass(frozen=True)
class ExecutionPlanGraphMetadata:
    node_id: str | None = None
    node_kind: str | None = None
    graph_path: str | None = None
    fanout_id: str | None = None
    branch_id: str | None = None
    loop_id: str | None = None
    loop_iteration: int | None = None
    source_refs: dict[str, Any] | None = None


@dataclass(frozen=True)
class PackageResolvedModelBinding:
    key: str
    name: str
    protocol_profile: str
    base_url: str
    model_id: str
    reasoning_effort: str | None
    capabilities: dict[str, Any]
    output_strategy_policy: str
    parallel_tool_calls_policy: str
    reasoning_policy: str
    streaming_policy: str
    probe_cache_ttl_seconds: int
    api_style: str
    timeout_seconds: int
    has_api_key: bool


@dataclass(frozen=True)
class PackageExecutionRequirements:
    requires_native_tool_calls: bool = False
    requires_structured_output: bool = False
    requires_parallel_tool_calls: bool = False
    requires_streaming: bool = False
    requires_reasoning_hints: bool = False
    native_tool_sources: tuple[str, ...] = ()
    structured_output_sources: tuple[str, ...] = ()
    parallel_tool_sources: tuple[str, ...] = ()
    streaming_sources: tuple[str, ...] = ()
    reasoning_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class PackageAgentExecutionRequirements:
    agent_key: str
    model_connection_key: str
    model_connection_field: str
    requirements: PackageExecutionRequirements


@dataclass(frozen=True)
class PackageCapabilityProfileGrant:
    key: str
    name: str
    description: str
    tool_keys: tuple[str, ...]


@dataclass(frozen=True)
class PackagePrivateMcpConfig:
    key: str
    name: str
    description: str
    transport: str
    command: str | None
    args: tuple[str, ...]
    url: str | None
    env: dict[str, str]
    headers: dict[str, str]
    query: dict[str, str]
    tool_keys: tuple[str, ...]
    tool_descriptors: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class PackageLocalOutputSchemaSpec:
    local_id: int
    key: str
    name: str
    description: str
    json_schema: dict[str, Any]


@dataclass(frozen=True)
class PackageRuntimeAgentSpec:
    local_id: int
    key: str
    name: str
    description: str
    model_binding: PackageResolvedModelBinding | None
    system_prompt: str
    input_schema: dict[str, Any]
    output_schema: PackageLocalOutputSchemaSpec
    capability_profiles: tuple[PackageCapabilityProfileGrant, ...]
    mcp_servers: tuple[PackagePrivateMcpConfig, ...]


@dataclass(frozen=True)
class PackageRuntimeOperationSpec:
    key: str
    kind: ExecutionPlanOperationKind
    slot: str
    method: str
    request: dict[str, Any]
    output_schema: PackageLocalOutputSchemaSpec
    timeout_seconds: int
    optional: bool


@dataclass(frozen=True)
class PackageExecutionStep:
    index: int
    agents: tuple[PackageRuntimeAgentSpec, ...]
    operations: tuple[PackageRuntimeOperationSpec, ...] = ()
    graph_metadata: ExecutionPlanGraphMetadata | None = None


@dataclass(frozen=True)
class PackageExecutionWorkflow:
    package_key: str
    key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    steps: tuple[PackageExecutionStep, ...]
    final_output: ExecutionPlanFinalOutput
    compiled_graph: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutionPlanAgent:
    slot: str
    agent_id: int
    agent_key: str
    agent_version: int
    output_schema_id: int
    output_schema_version: int
    wiring: dict[str, ExecutionPlanSource]
    package_runtime_agent: PackageRuntimeAgentSpec
    optional: bool = False
    input_mode: ExecutionPlanInputMode = "wired"
    graph_metadata: ExecutionPlanGraphMetadata | None = None


@dataclass(frozen=True)
class ExecutionPlanOperation:
    slot: str
    operation_key: str
    operation_kind: ExecutionPlanOperationKind
    output_schema_id: int
    output_schema_version: int
    request: dict[str, Any]
    method: str | None = None
    timeout_seconds: int | None = None
    optional: bool = False
    graph_metadata: ExecutionPlanGraphMetadata | None = None
    package_runtime_operation: PackageRuntimeOperationSpec | None = None


@dataclass(frozen=True)
class ExecutionPlanStep:
    index: int
    agents: tuple[ExecutionPlanAgent, ...]
    operations: tuple[ExecutionPlanOperation, ...] = ()
    graph_metadata: ExecutionPlanGraphMetadata | None = None
    package_step: PackageExecutionStep | None = None


@dataclass(frozen=True)
class ExecutionPlanFinalOutput:
    step_index: int
    slot: str
    path: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    target: ExecutionPlanTarget
    input_schema: dict[str, Any]
    steps: tuple[ExecutionPlanStep, ...]
    final_output: ExecutionPlanFinalOutput
    package_workflow: PackageExecutionWorkflow | None = None
    package_ownership: PackageExecutionOwnership | None = None


__all__ = [
    "ExecutionPlan",
    "ExecutionPlanAgent",
    "ExecutionPlanFinalOutput",
    "ExecutionPlanGraphMetadata",
    "ExecutionPlanInputMode",
    "ExecutionPlanOperation",
    "ExecutionPlanOperationKind",
    "ExecutionPlanSource",
    "ExecutionPlanSourceKind",
    "ExecutionPlanStep",
    "ExecutionPlanTarget",
    "ExecutionPlanTargetKind",
    "PackageExecutionOwnership",
    "PackageExecutionRequirements",
    "PackageAgentExecutionRequirements",
    "PackageCapabilityProfileGrant",
    "PackageExecutionStep",
    "PackageExecutionWorkflow",
    "PackageLocalOutputSchemaSpec",
    "PackagePrivateMcpConfig",
    "PackageResolvedModelBinding",
    "PackageRuntimeAgentSpec",
    "PackageRuntimeOperationSpec",
]
