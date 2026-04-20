from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, NoReturn

from fastapi import status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error, validation_error
from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.models.workflow import Workflow
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowListRead,
    WorkflowOutputAgentWrite,
    WorkflowOutputSlotWrite,
    WorkflowRead,
    WorkflowStatus,
    WorkflowUpdate,
    WorkflowWireSource,
)
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
    SchemaArray,
    SchemaDiscriminatedUnion,
    SchemaEnum,
    SchemaField,
    SchemaLiteral,
    SchemaNode,
    SchemaObject,
    SchemaPrimitive,
    SchemaRef,
)


@dataclass
class _ResolvedSlot:
    step_index: int
    slot: str
    agent: Agent
    output_schema: OutputSchema
    schema: SchemaNode
    optional: bool


class WorkflowService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = WorkflowRepository(session)
        self.agent_repository = AgentRepository(session)
        self.output_schema_repository = OutputSchemaRepository(session)
        self.schema_compiler = OutputSchemaCompiler(self.output_schema_repository)
        self._stored_schema_node_cache: dict[tuple[str, int], SchemaNode] = {}

    def list_workflows(
        self,
        *,
        status_filter: WorkflowStatus | None = None,
    ) -> WorkflowListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None,
        )
        return WorkflowListRead(items=[self._to_read_model(item) for item in items])

    def get_workflow(self, workflow_id: int, *, version: int | None = None) -> WorkflowRead:
        return self._to_read_model(self._resolve_model(workflow_id, version=version))

    def create_workflow(self, payload: WorkflowCreate) -> WorkflowRead:
        if self.repository.list_versions(payload.key):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_duplicate_key",
                message="A workflow with this key already exists",
            )

        state = self._build_state(
            name=payload.name,
            description=payload.description,
            input_schema=payload.input_schema,
            steps=payload.steps,
            output_spec=payload.output_spec,
        )
        workflow = Workflow(
            key=payload.key,
            version=1,
            status=WorkflowStatus.PUBLISHED.value,
            **state,
        )
        try:
            self.repository.add(workflow)
            self.session.commit()
            self.session.refresh(workflow)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(workflow)

    def update_workflow(self, workflow_id: int, payload: WorkflowUpdate) -> WorkflowRead:
        source = self._get_model(workflow_id)
        state = self._build_state(
            name=payload.name,
            description=payload.description,
            input_schema=payload.input_schema,
            steps=payload.steps,
            output_spec=payload.output_spec,
        )
        workflow = Workflow(
            key=source.key,
            version=self._next_version(source.key),
            status=WorkflowStatus.PUBLISHED.value,
            **state,
        )

        current_published = self.repository.get_published_by_key(source.key)
        try:
            if current_published is not None:
                current_published.status = WorkflowStatus.DEPRECATED.value
                self.session.flush()
            self.repository.add(workflow)
            self.session.commit()
            self.session.refresh(workflow)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(workflow)

    def archive_workflow(self, workflow_id: int) -> WorkflowRead:
        workflow = self._get_model(workflow_id)
        if workflow.status == WorkflowStatus.ARCHIVED.value:
            return self._to_read_model(workflow)

        try:
            workflow.status = WorkflowStatus.ARCHIVED.value
            self.session.commit()
            self.session.refresh(workflow)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(workflow)

    def _build_state(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        steps: list[Any],
        output_spec: Any,
    ) -> dict[str, Any]:
        normalized_input_schema = self._normalize_input_schema(input_schema)
        input_node = self._parse_input_schema_node(
            normalized_input_schema,
            field="inputSchema",
        )
        resolved_slots: dict[tuple[int, str], _ResolvedSlot] = {}
        normalized_steps: list[dict[str, Any]] = []
        aggregate_budget = Decimal("0")

        for step_offset, step in enumerate(steps, start=1):
            step_field = f"steps[{step_offset - 1}]"
            if step.index != step_offset:
                self._raise_validation(
                    f"{step_field}.index",
                    f"Step indices must be sequential starting at 1; expected {step_offset}",
                )

            step_slots: set[str] = set()
            normalized_agents: list[dict[str, Any]] = []
            for agent_offset, agent_ref in enumerate(step.agents):
                agent_field = f"{step_field}.agents[{agent_offset}]"
                if agent_ref.slot in step_slots:
                    self._raise_validation(
                        f"{agent_field}.slot",
                        "Duplicate slot name within the same step",
                    )
                step_slots.add(agent_ref.slot)

                agent = self._resolve_agent(
                    agent_ref.agent_key,
                    agent_ref.agent_version,
                    field=f"{agent_field}.agentKey",
                )
                output_schema = self._resolve_agent_output_schema(
                    agent,
                    field=f"{agent_field}.agentKey",
                )
                agent_input_node = self._parse_input_schema_node(
                    agent.input_schema,
                    field=f"{agent_field}.agentKey",
                )
                output_node = self._parse_output_schema_node(
                    output_schema,
                    field=f"{agent_field}.agentKey",
                )
                normalized_wiring = self._normalize_wiring(
                    field_prefix=f"{agent_field}.wiring",
                    wiring=agent_ref.wiring,
                    target_node=agent_input_node,
                    input_node=input_node,
                    resolved_slots=resolved_slots,
                    current_step_index=step.index,
                )
                normalized_agents.append(
                    {
                        "slot": agent_ref.slot,
                        "agentId": agent.id,
                        "agentKey": agent.key,
                        "agentVersion": agent.version,
                        "outputSchemaId": output_schema.id,
                        "outputSchemaVersion": output_schema.version,
                        "wiring": normalized_wiring,
                        "optional": agent_ref.optional,
                        "budgetUsd": str(agent.budget_usd),
                    }
                )
                resolved_slots[(step.index, agent_ref.slot)] = _ResolvedSlot(
                    step_index=step.index,
                    slot=agent_ref.slot,
                    agent=agent,
                    output_schema=output_schema,
                    schema=output_node,
                    optional=agent_ref.optional,
                )
                aggregate_budget += agent.budget_usd
            normalized_steps.append({"index": step.index, "agents": normalized_agents})

        normalized_output_spec, output_budget = self._normalize_output_spec(
            output_spec=output_spec,
            input_node=input_node,
            resolved_slots=resolved_slots,
            current_step_index=len(steps) + 1,
        )
        aggregate_budget += output_budget
        return {
            "name": name,
            "description": description,
            "input_schema": normalized_input_schema,
            "steps": normalized_steps,
            "output_spec": normalized_output_spec,
            "aggregate_budget_usd": aggregate_budget,
        }

    def _normalize_output_spec(
        self,
        *,
        output_spec: WorkflowOutputSlotWrite | WorkflowOutputAgentWrite,
        input_node: SchemaNode,
        resolved_slots: dict[tuple[int, str], _ResolvedSlot],
        current_step_index: int,
    ) -> tuple[dict[str, Any], Decimal]:
        if isinstance(output_spec, WorkflowOutputSlotWrite):
            resolved_slot = self._get_resolved_slot(
                step_index=output_spec.step_index,
                slot=output_spec.slot,
                field="outputSpec.slot",
                resolved_slots=resolved_slots,
                current_step_index=current_step_index,
            )
            if resolved_slot.optional:
                self._raise_validation(
                    "outputSpec.slot",
                    "Final output cannot reference an optional slot",
                )
            if output_spec.path is not None:
                self._resolve_node_path(
                    resolved_slot.schema,
                    output_spec.path,
                    field="outputSpec.path",
                )
            return (
                {
                    "kind": "slot",
                    "stepIndex": output_spec.step_index,
                    "slot": output_spec.slot,
                    "path": output_spec.path,
                    "agentId": resolved_slot.agent.id,
                    "agentKey": resolved_slot.agent.key,
                    "agentVersion": resolved_slot.agent.version,
                    "outputSchemaId": resolved_slot.output_schema.id,
                    "outputSchemaVersion": resolved_slot.output_schema.version,
                },
                Decimal("0"),
            )

        agent = self._resolve_agent(
            output_spec.agent_key,
            output_spec.agent_version,
            field="outputSpec.agentKey",
        )
        output_schema = self._resolve_agent_output_schema(agent, field="outputSpec.agentKey")
        agent_input_node = self._parse_input_schema_node(
            agent.input_schema,
            field="outputSpec.agentKey",
        )
        normalized_wiring = self._normalize_wiring(
            field_prefix="outputSpec.wiring",
            wiring=output_spec.wiring,
            target_node=agent_input_node,
            input_node=input_node,
            resolved_slots=resolved_slots,
            current_step_index=current_step_index,
        )
        return (
            {
                "kind": "agent",
                "agentId": agent.id,
                "agentKey": agent.key,
                "agentVersion": agent.version,
                "outputSchemaId": output_schema.id,
                "outputSchemaVersion": output_schema.version,
                "wiring": normalized_wiring,
            },
            agent.budget_usd,
        )

    def _normalize_wiring(
        self,
        *,
        field_prefix: str,
        wiring: dict[str, WorkflowWireSource],
        target_node: SchemaNode,
        input_node: SchemaNode,
        resolved_slots: dict[tuple[int, str], _ResolvedSlot],
        current_step_index: int,
    ) -> dict[str, dict[str, Any]]:
        target_fields = self._object_field_map(target_node, field=field_prefix)
        normalized_wiring: dict[str, dict[str, Any]] = {}

        for target_name, source in wiring.items():
            field_name = f"{field_prefix}.{target_name}"
            target_field = target_fields.get(target_name)
            if target_field is None:
                self._raise_validation(
                    field_name,
                    f"Input field {target_name!r} is not defined on the target schema",
                )
            source_node, source_optional, normalized_source = self._resolve_source(
                source,
                input_node=input_node,
                resolved_slots=resolved_slots,
                current_step_index=current_step_index,
                field=field_name,
            )
            if source_optional and target_field.required:
                self._raise_validation(
                    field_name,
                    "Optional slots can only wire into optional target fields",
                )
            if not self._is_compatible(source_node, target_field.schema):
                self._raise_validation(
                    field_name,
                    "Wired source type is not compatible with the target field schema",
                )
            normalized_wiring[target_name] = normalized_source

        for target_name, target_field in target_fields.items():
            if target_field.required and target_name not in normalized_wiring:
                self._raise_validation(
                    f"{field_prefix}.{target_name}",
                    "Required input field is not wired",
                )
        return normalized_wiring

    def _resolve_source(
        self,
        source: WorkflowWireSource,
        *,
        input_node: SchemaNode,
        resolved_slots: dict[tuple[int, str], _ResolvedSlot],
        current_step_index: int,
        field: str,
    ) -> tuple[SchemaNode, bool, dict[str, Any]]:
        if source.source == "input":
            resolved_node = self._resolve_node_path(input_node, source.path, field=field)
            payload: dict[str, Any] = {"from": "input"}
            if source.path is not None:
                payload["path"] = source.path
            return resolved_node, False, payload

        resolved_slot = self._get_resolved_slot(
            step_index=int(source.step_index or 0),
            slot=str(source.slot or ""),
            field=field,
            resolved_slots=resolved_slots,
            current_step_index=current_step_index,
        )
        resolved_node = self._resolve_node_path(
            resolved_slot.schema,
            source.path,
            field=field,
        )
        payload = {
            "from": "step",
            "stepIndex": resolved_slot.step_index,
            "slot": resolved_slot.slot,
        }
        if source.path is not None:
            payload["path"] = source.path
        return resolved_node, resolved_slot.optional, payload

    def _get_resolved_slot(
        self,
        *,
        step_index: int,
        slot: str,
        field: str,
        resolved_slots: dict[tuple[int, str], _ResolvedSlot],
        current_step_index: int,
    ) -> _ResolvedSlot:
        if step_index >= current_step_index:
            self._raise_validation(
                field,
                "Slot references must point to an earlier step",
            )
        resolved_slot = resolved_slots.get((step_index, slot))
        if resolved_slot is None:
            self._raise_validation(
                field,
                f"Slot {slot!r} was not found on step {step_index}",
            )
        return resolved_slot

    def _resolve_node_path(
        self,
        node: SchemaNode,
        path: str | None,
        *,
        field: str,
    ) -> SchemaNode:
        current = self._dereference_node(node)
        if path is None:
            return current
        for segment in path.split("."):
            current = self._dereference_node(current)
            if not isinstance(current, SchemaObject):
                self._raise_validation(
                    field,
                    f"Path {path!r} does not resolve to a field on the source schema",
                )
            field_map = {item.name: item for item in current.fields}
            child = field_map.get(segment)
            if child is None:
                self._raise_validation(
                    field,
                    f"Path {path!r} does not resolve to a field on the source schema",
                )
            current = child.schema
        return self._dereference_node(current)

    def _object_field_map(self, node: SchemaNode, *, field: str) -> dict[str, SchemaField]:
        resolved = self._dereference_node(node)
        if not isinstance(resolved, SchemaObject):
            self._raise_validation(field, "Target schema must be an object")
        return {item.name: item for item in resolved.fields}

    def _is_compatible(self, source: SchemaNode, target: SchemaNode) -> bool:
        resolved_source = self._dereference_node(source)
        resolved_target = self._dereference_node(target)
        source_variants = (
            list(resolved_source.variants)
            if isinstance(resolved_source, SchemaDiscriminatedUnion)
            else [resolved_source]
        )
        target_variants = (
            list(resolved_target.variants)
            if isinstance(resolved_target, SchemaDiscriminatedUnion)
            else [resolved_target]
        )
        return all(
            any(
                self._is_non_union_compatible(source_variant, target_variant)
                for target_variant in target_variants
            )
            for source_variant in source_variants
        )

    def _is_non_union_compatible(self, source: SchemaNode, target: SchemaNode) -> bool:
        resolved_source = self._dereference_node(source)
        resolved_target = self._dereference_node(target)

        if isinstance(resolved_target, SchemaLiteral):
            possible_values = self._possible_values(resolved_source)
            return possible_values is not None and set(possible_values).issubset(
                {resolved_target.value}
            )
        if isinstance(resolved_target, SchemaEnum):
            possible_values = self._possible_values(resolved_source)
            return possible_values is not None and set(possible_values).issubset(
                set(resolved_target.values)
            )
        if isinstance(resolved_target, SchemaPrimitive):
            source_kind = self._primitive_kind(resolved_source)
            return source_kind is not None and self._primitive_kind_compatible(
                source_kind,
                resolved_target.schema_type,
            )
        if isinstance(resolved_target, SchemaArray):
            if not isinstance(resolved_source, SchemaArray):
                return False
            return self._is_compatible(resolved_source.items, resolved_target.items)
        if not isinstance(resolved_target, SchemaObject):
            return False
        if not isinstance(resolved_source, SchemaObject):
            return False
        if (
            resolved_source.allow_additional_properties
            and not resolved_target.allow_additional_properties
        ):
            return False

        source_fields = {item.name: item for item in resolved_source.fields}
        target_fields = {item.name: item for item in resolved_target.fields}
        for target_name, target_field in target_fields.items():
            source_field = source_fields.get(target_name)
            if target_field.required:
                if source_field is None or not source_field.required:
                    return False
            if source_field is not None and not self._is_compatible(
                source_field.schema,
                target_field.schema,
            ):
                return False
        if not resolved_target.allow_additional_properties:
            for source_name in source_fields:
                if source_name not in target_fields:
                    return False
        return True

    def _possible_values(self, node: SchemaNode) -> tuple[Any, ...] | None:
        resolved = self._dereference_node(node)
        if isinstance(resolved, SchemaLiteral):
            return (resolved.value,)
        if isinstance(resolved, SchemaEnum):
            return tuple(resolved.values)
        return None

    def _primitive_kind(self, node: SchemaNode) -> str | None:
        resolved = self._dereference_node(node)
        if isinstance(resolved, SchemaPrimitive):
            return resolved.schema_type
        values = self._possible_values(resolved)
        if values is None or not values:
            return None
        value = values[0]
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, str):
            return "string"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        return None

    @staticmethod
    def _primitive_kind_compatible(source_kind: str, target_kind: str) -> bool:
        return source_kind == target_kind or (source_kind == "integer" and target_kind == "number")

    def _dereference_node(self, node: SchemaNode) -> SchemaNode:
        current = node
        while isinstance(current, SchemaRef):
            cache_key = (current.key, current.version)
            cached = self._stored_schema_node_cache.get(cache_key)
            if cached is None:
                row = self.output_schema_repository.resolve_registry_ref(
                    current.key,
                    current.version,
                )
                if row is None:
                    raise OutputSchemaCompilerError(
                        f"Shared registry ref {current.key!r} v{current.version} was not found"
                    )
                cached = self.schema_compiler.parse_stored_schema_node(row)
                self._stored_schema_node_cache[cache_key] = cached
            current = cached
        return current

    def _normalize_input_schema(self, input_schema: dict[str, Any]) -> dict[str, Any]:
        try:
            prepared = self.schema_compiler.normalize_payload(
                builder=None,
                json_schema=input_schema,
            )
        except OutputSchemaValidationFailure as exc:
            raise validation_error(
                "Workflow validation failed",
                [self._rewrite_schema_issue(issue) for issue in exc.issues],
            ) from exc

        if prepared.json_schema.get("type") != "object":
            self._raise_validation("inputSchema", "Input schema must be an object schema")

        try:
            self._build_input_model(prepared.json_schema)
        except OutputSchemaCompilerError as exc:
            self._raise_validation("inputSchema", str(exc))
        return prepared.json_schema

    def _parse_input_schema_node(
        self,
        input_schema: dict[str, Any],
        *,
        field: str,
    ) -> SchemaNode:
        try:
            return self.schema_compiler.parse_json_schema_node(
                input_schema,
                path=field,
            )
        except OutputSchemaCompilerError as exc:
            self._raise_validation(field, str(exc))

    def _parse_output_schema_node(self, schema: OutputSchema, *, field: str) -> SchemaNode:
        cache_key = (schema.key, schema.version)
        cached = self._stored_schema_node_cache.get(cache_key)
        if cached is not None:
            return cached
        try:
            node = self.schema_compiler.parse_stored_schema_node(schema)
        except OutputSchemaCompilerError as exc:
            self._raise_validation(field, str(exc))
        self._stored_schema_node_cache[cache_key] = node
        return node

    def _resolve_agent(self, key: str, version: int | None, *, field: str) -> Agent:
        agent = self.agent_repository.resolve_version(key, version)
        if agent is None:
            issue = (
                f"Agent {key!r} was not found"
                if version is None
                else f"Agent {key!r} version {version} was not found"
            )
            self._raise_validation(field, issue)
        return agent

    def _resolve_agent_output_schema(self, agent: Agent, *, field: str) -> OutputSchema:
        output_schema = self.output_schema_repository.get(agent.output_schema_id)
        if output_schema is None or output_schema.version != agent.output_schema_version:
            self._raise_validation(
                field,
                f"Agent {agent.key!r} references a missing output schema version",
            )
        return output_schema

    def _resolve_model(self, workflow_id: int, *, version: int | None) -> Workflow:
        anchor = self._get_model(workflow_id)
        if version is None:
            return anchor
        workflow = self.repository.get_by_key_version(anchor.key, version)
        if workflow is None:
            raise not_found_error("Workflow")
        return workflow

    def _get_model(self, workflow_id: int) -> Workflow:
        workflow = self.repository.get(workflow_id)
        if workflow is None:
            raise not_found_error("Workflow")
        return workflow

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _build_input_model(self, input_schema: dict[str, Any]) -> type[BaseModel]:
        candidate = OutputSchema(
            key="workflow_input_schema_validation",
            version=1,
            status=WorkflowStatus.PUBLISHED.value,
            kind="standalone",
            name="Workflow Input Schema",
            description="Workflow input schema validation candidate",
            json_schema=input_schema,
            registry_refs=[],
        )
        return self.schema_compiler.build_runtime_model(candidate)

    def _to_read_model(self, workflow: Workflow) -> WorkflowRead:
        return WorkflowRead.model_validate(
            {
                "id": workflow.id,
                "key": workflow.key,
                "version": workflow.version,
                "status": workflow.status,
                "name": workflow.name,
                "description": workflow.description,
                "inputSchema": workflow.input_schema,
                "steps": workflow.steps,
                "outputSpec": workflow.output_spec,
                "aggregateBudgetUsd": workflow.aggregate_budget_usd,
                "createdAt": workflow.created_at,
                "updatedAt": workflow.updated_at,
            }
        )

    @staticmethod
    def _rewrite_schema_issue(issue: dict[str, str]) -> dict[str, str]:
        field = issue.get("field", "inputSchema")
        if field == "jsonSchema":
            mapped_field = "inputSchema"
        elif field.startswith("jsonSchema."):
            mapped_field = field.replace("jsonSchema", "inputSchema", 1)
        else:
            mapped_field = field
        return {"field": mapped_field, "issue": issue.get("issue", "Invalid schema")}

    @staticmethod
    def _raise_validation(field: str, issue: str) -> NoReturn:
        raise validation_error(
            "Workflow validation failed",
            [{"field": field, "issue": issue}],
        )


__all__ = ["WorkflowService"]
