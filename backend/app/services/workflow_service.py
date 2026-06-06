from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, NoReturn, cast

from fastapi import status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error, validation_error
from app.models.agent import Agent
from app.models.output_schema import OutputSchema
from app.models.workflow import (
    TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
    WORKFLOW_MANIFEST_API_VERSION,
    Workflow,
)
from app.repositories.agent import AgentRepository
from app.repositories.output_schema import OutputSchemaRepository
from app.repositories.workflow import WorkflowRepository
from app.schemas.workflow import (
    WorkflowCreate,
    WorkflowCreateRequest,
    WorkflowListRead,
    WorkflowManifestValidationMetadata,
    WorkflowManifestValidationRead,
    WorkflowManifestValidationRequest,
    WorkflowOutputSlotWrite,
    WorkflowRead,
    WorkflowStatus,
    WorkflowUpdate,
    WorkflowUpdateRequest,
    WorkflowWireSource,
)
from app.schemas.workflow_manifest import (
    WorkflowManifestDiagnostic,
    WorkflowManifestDiagnosticSeverity,
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
from app.services.workflow_manifest_compiler import (
    WorkflowManifestCompilerError,
    compile_workflow_manifest,
)
from app.services.workflow_manifest_parser import (
    locate_workflow_manifest_path,
    parse_workflow_manifest,
)

_COMPILED_GRAPH_STORAGE_KEY = "compiledGraph"


@dataclass
class _ResolvedSlot:
    step_index: int
    slot: str
    agent: Agent
    output_schema: OutputSchema
    schema: SchemaNode
    optional: bool


@dataclass
class _PreparedManifestWrite:
    payload: WorkflowCreate
    state: dict[str, object]
    metadata: WorkflowManifestValidationMetadata
    compiled_payload: dict[str, object]
    compiled_graph: dict[str, object] | None


class _WorkflowManifestDiagnosticsError(ValueError):
    def __init__(self, diagnostics: list[WorkflowManifestDiagnostic]) -> None:
        super().__init__("Workflow manifest validation failed")
        self.diagnostics: list[WorkflowManifestDiagnostic] = diagnostics


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

    def validate_workflow_manifest(
        self,
        payload: WorkflowManifestValidationRequest,
    ) -> WorkflowManifestValidationRead:
        try:
            prepared = self._prepare_manifest_write(payload.manifest_source)
        except _WorkflowManifestDiagnosticsError as exc:
            return WorkflowManifestValidationRead(diagnostics=exc.diagnostics)
        return WorkflowManifestValidationRead(
            diagnostics=[],
            metadata=prepared.metadata,
            compiled_payload=prepared.compiled_payload,
            compiled_graph=prepared.compiled_graph,
            run_input_schema=cast(dict[str, object], prepared.state["input_schema"]),
        )

    def create_workflow(self, payload: WorkflowCreate | WorkflowCreateRequest) -> WorkflowRead:
        prepared_manifest: _PreparedManifestWrite | None = None
        compiled_payload: WorkflowCreate
        if isinstance(payload, WorkflowCreateRequest):
            if payload.manifest_source is not None:
                prepared_manifest = self._prepare_manifest_write_or_raise(payload.manifest_source)
                compiled_payload = prepared_manifest.payload
            else:
                compiled_payload = payload.to_workflow_create()
        else:
            compiled_payload = payload

        if self.repository.list_versions(compiled_payload.key):
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="workflow_duplicate_key",
                message="A workflow with this key already exists",
            )

        state = (
            prepared_manifest.state
            if prepared_manifest is not None
            else self._build_state(
                name=compiled_payload.name,
                description=compiled_payload.description,
                input_schema=compiled_payload.input_schema,
                steps=compiled_payload.steps,
                output_spec=compiled_payload.output_spec,
            )
        )
        workflow = Workflow(
            key=compiled_payload.key,
            version=1,
            status=WorkflowStatus.PUBLISHED.value,
            **state,
        )
        try:
            _ = self.repository.add(workflow)
            self.session.commit()
            self.session.refresh(workflow)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(workflow)

    def update_workflow(
        self,
        workflow_id: int,
        payload: WorkflowUpdate | WorkflowUpdateRequest,
    ) -> WorkflowRead:
        source = self._get_model(workflow_id)
        prepared_manifest: _PreparedManifestWrite | None = None
        compiled_payload: WorkflowUpdate
        if isinstance(payload, WorkflowUpdateRequest):
            if payload.manifest_source is not None:
                prepared_manifest = self._prepare_manifest_write_or_raise(payload.manifest_source)
                if prepared_manifest.payload.key != source.key:
                    diagnostic = self._manifest_diagnostic(
                        payload.manifest_source,
                        "metadata.key",
                        f"Manifest key must remain {source.key!r} for workflow updates",
                    )
                    self._raise_manifest_validation([diagnostic])
                compiled_payload = WorkflowUpdate.model_validate(
                    prepared_manifest.payload.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude={"key"},
                    )
                )
            else:
                compiled_payload = payload.to_workflow_update()
        else:
            compiled_payload = payload

        state = (
            prepared_manifest.state
            if prepared_manifest is not None
            else self._build_state(
                name=compiled_payload.name,
                description=compiled_payload.description,
                input_schema=compiled_payload.input_schema,
                steps=compiled_payload.steps,
                output_spec=compiled_payload.output_spec,
            )
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
            _ = self.repository.add(workflow)
            self.session.commit()
            self.session.refresh(workflow)
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(workflow)

    def delete_workflow(self, workflow_id: int) -> None:
        workflow = self._get_model(workflow_id)
        try:
            self.repository.delete(workflow)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def _build_state(
        self,
        *,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        steps: list[Any],
        output_spec: Any,
        manifest_api_version: str = WORKFLOW_MANIFEST_API_VERSION,
        manifest_source: str = TEMPORARY_WORKFLOW_MANIFEST_SOURCE,
        compiled_graph: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        normalized_input_schema = self._normalize_input_schema(input_schema)
        input_node = self._parse_input_schema_node(
            normalized_input_schema,
            field="inputSchema",
        )
        resolved_slots: dict[tuple[int, str], _ResolvedSlot] = {}
        normalized_steps: list[dict[str, Any]] = []

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
            normalized_steps.append({"index": step.index, "agents": normalized_agents})

        normalized_output_spec = self._normalize_output_spec(
            output_spec=output_spec,
            resolved_slots=resolved_slots,
            current_step_index=len(steps) + 1,
        )
        return {
            "name": name,
            "description": description,
            "manifest_api_version": manifest_api_version,
            "manifest_source": manifest_source,
            "input_schema": normalized_input_schema,
            "steps": normalized_steps,
            "output_spec": self._store_compiled_graph(
                normalized_output_spec,
                compiled_graph,
            ),
        }

    def _prepare_manifest_write_or_raise(self, manifest_source: str) -> _PreparedManifestWrite:
        try:
            return self._prepare_manifest_write(manifest_source)
        except _WorkflowManifestDiagnosticsError as exc:
            self._raise_manifest_validation(exc.diagnostics)

    def _prepare_manifest_write(self, manifest_source: str) -> _PreparedManifestWrite:
        parse_result = parse_workflow_manifest(manifest_source)
        if parse_result.manifest is None or parse_result.diagnostics:
            raise _WorkflowManifestDiagnosticsError(parse_result.diagnostics)

        manifest = parse_result.manifest
        try:
            compiled_payload = compile_workflow_manifest(
                manifest_source,
                schema_compiler=self.schema_compiler,
            )
        except WorkflowManifestCompilerError as exc:
            raise _WorkflowManifestDiagnosticsError(exc.diagnostics) from exc
        compiled_graph = self._compiled_graph_from_payload(compiled_payload)
        core_compiled_payload = self._compiled_payload_without_graph(compiled_payload)
        payload = WorkflowCreate.model_validate(core_compiled_payload)
        try:
            state = self._build_state(
                name=payload.name,
                description=payload.description,
                input_schema=payload.input_schema,
                steps=payload.steps,
                output_spec=payload.output_spec,
                manifest_api_version=manifest.api_version,
                manifest_source=manifest_source,
                compiled_graph=compiled_graph,
            )
        except ApiError as exc:
            raise _WorkflowManifestDiagnosticsError(
                self._api_error_to_manifest_diagnostics(manifest_source, exc.details)
            ) from exc
        metadata = WorkflowManifestValidationMetadata(
            api_version=manifest.api_version,
            key=manifest.metadata.key,
            name=manifest.metadata.name,
            description=manifest.metadata.description,
        )
        return _PreparedManifestWrite(
            payload=payload,
            state=state,
            metadata=metadata,
            compiled_payload=core_compiled_payload,
            compiled_graph=compiled_graph,
        )

    @staticmethod
    def _compiled_graph_from_payload(
        compiled_payload: dict[str, object],
    ) -> dict[str, object] | None:
        compiled_graph = compiled_payload.get(_COMPILED_GRAPH_STORAGE_KEY)
        if compiled_graph is None:
            return None
        return cast(dict[str, object], compiled_graph)

    @staticmethod
    def _compiled_payload_without_graph(
        compiled_payload: dict[str, object],
    ) -> dict[str, object]:
        return {
            key: value
            for key, value in compiled_payload.items()
            if key != _COMPILED_GRAPH_STORAGE_KEY
        }

    @staticmethod
    def _store_compiled_graph(
        output_spec: dict[str, Any],
        compiled_graph: dict[str, object] | None,
    ) -> dict[str, Any]:
        if compiled_graph is None:
            return output_spec
        return output_spec | {_COMPILED_GRAPH_STORAGE_KEY: compiled_graph}

    @staticmethod
    def _stored_compiled_graph(output_spec: dict[str, Any]) -> dict[str, object] | None:
        compiled_graph = output_spec.get(_COMPILED_GRAPH_STORAGE_KEY)
        if compiled_graph is None:
            return None
        return cast(dict[str, object], compiled_graph)

    @staticmethod
    def _output_spec_without_compiled_graph(output_spec: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in output_spec.items() if key != _COMPILED_GRAPH_STORAGE_KEY
        }

    def _api_error_to_manifest_diagnostics(
        self,
        manifest_source: str,
        details: list[dict[str, Any]],
    ) -> list[WorkflowManifestDiagnostic]:
        if not details:
            return [
                self._manifest_diagnostic(
                    manifest_source,
                    "$",
                    "Workflow manifest validation failed",
                )
            ]

        diagnostics: list[WorkflowManifestDiagnostic] = []
        for detail in details:
            field = str(detail.get("field") or "$")
            issue = str(detail.get("issue") or "Invalid workflow manifest value")
            diagnostics.append(
                self._manifest_diagnostic(
                    manifest_source,
                    self._workflow_field_to_manifest_path(field),
                    issue,
                )
            )
        return diagnostics

    @staticmethod
    def _workflow_field_to_manifest_path(field: str) -> str:
        agent_field_match = re.fullmatch(
            r"steps\[(\d+)\]\.agents\[(\d+)\]\.agentKey",
            field,
        )
        if agent_field_match is not None:
            return f"steps[{agent_field_match.group(1)}].agents[{agent_field_match.group(2)}].uses"

        wiring_match = re.fullmatch(
            r"steps\[(\d+)\]\.agents\[(\d+)\]\.wiring(?:\.(.+))?",
            field,
        )
        if wiring_match is not None:
            path = f"steps[{wiring_match.group(1)}].agents[{wiring_match.group(2)}].with"
            target_field = wiring_match.group(3)
            if target_field:
                path += f".{target_field}"
            return path

        if field.startswith("outputSpec"):
            return "output.from"
        if field.startswith("inputSchema"):
            return field
        return field

    @staticmethod
    def _manifest_diagnostic(
        manifest_source: str,
        path: str,
        message: str,
    ) -> WorkflowManifestDiagnostic:
        line, column = locate_workflow_manifest_path(manifest_source, path)
        return WorkflowManifestDiagnostic(
            severity=WorkflowManifestDiagnosticSeverity.ERROR,
            message=message,
            path=path,
            line=line,
            column=column,
        )

    @staticmethod
    def _manifest_diagnostic_detail(diagnostic: WorkflowManifestDiagnostic) -> dict[str, object]:
        return {
            "field": "manifestSource",
            "issue": diagnostic.message,
            "severity": diagnostic.severity.value,
            "path": diagnostic.path,
            "line": diagnostic.line,
            "column": diagnostic.column,
        }

    def _raise_manifest_validation(
        self,
        diagnostics: list[WorkflowManifestDiagnostic],
    ) -> NoReturn:
        raise validation_error(
            "Workflow manifest validation failed",
            [self._manifest_diagnostic_detail(diagnostic) for diagnostic in diagnostics],
        )

    def _normalize_output_spec(
        self,
        *,
        output_spec: WorkflowOutputSlotWrite,
        resolved_slots: dict[tuple[int, str], _ResolvedSlot],
        current_step_index: int,
    ) -> dict[str, Any]:
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
        return {
            "kind": "slot",
            "stepIndex": output_spec.step_index,
            "slot": output_spec.slot,
            "path": output_spec.path,
            "agentId": resolved_slot.agent.id,
            "agentKey": resolved_slot.agent.key,
            "agentVersion": resolved_slot.agent.version,
            "outputSchemaId": resolved_slot.output_schema.id,
            "outputSchemaVersion": resolved_slot.output_schema.version,
        }

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
                "manifestApiVersion": workflow.manifest_api_version,
                "manifestSource": workflow.manifest_source,
                "inputSchema": workflow.input_schema,
                "steps": workflow.steps,
                "outputSpec": self._output_spec_without_compiled_graph(workflow.output_spec),
                "compiledGraph": self._stored_compiled_graph(workflow.output_spec),
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
