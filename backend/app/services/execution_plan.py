from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

ExecutionPlanInputMode = Literal["passthrough", "wired"]
ExecutionPlanTargetKind = Literal["agent", "workflow"]
ExecutionPlanSourceKind = Literal["input", "step"]


@dataclass(frozen=True)
class ExecutionPlanTarget:
    kind: ExecutionPlanTargetKind
    id: int
    key: str
    version: int


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
class ExecutionPlanAgent:
    slot: str
    agent_id: int
    agent_key: str
    agent_version: int
    output_schema_id: int
    output_schema_version: int
    wiring: dict[str, ExecutionPlanSource]
    optional: bool = False
    input_mode: ExecutionPlanInputMode = "wired"
    graph_metadata: ExecutionPlanGraphMetadata | None = None


@dataclass(frozen=True)
class ExecutionPlanStep:
    index: int
    agents: tuple[ExecutionPlanAgent, ...]
    graph_metadata: ExecutionPlanGraphMetadata | None = None


@dataclass(frozen=True)
class ExecutionPlanFinalOutput:
    step_index: int
    slot: str
    path: str | None = None


@dataclass(frozen=True)
class ExecutionPlan:
    target: ExecutionPlanTarget
    input_schema: dict[str, Any]
    aggregate_budget_usd: Decimal
    steps: tuple[ExecutionPlanStep, ...]
    final_output: ExecutionPlanFinalOutput


__all__ = [
    "ExecutionPlan",
    "ExecutionPlanAgent",
    "ExecutionPlanFinalOutput",
    "ExecutionPlanGraphMetadata",
    "ExecutionPlanInputMode",
    "ExecutionPlanSource",
    "ExecutionPlanSourceKind",
    "ExecutionPlanStep",
    "ExecutionPlanTarget",
    "ExecutionPlanTargetKind",
]
