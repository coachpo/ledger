# pyright: reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import cast

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.events import AliasEvent, ScalarEvent

from app.schemas.workflow_manifest import (
    WORKFLOW_MANIFEST_V1_API_VERSION,
    WORKFLOW_MANIFEST_V2_API_VERSION,
    WorkflowManifest,
    WorkflowManifestDiagnostic,
    WorkflowManifestDiagnosticSeverity,
    WorkflowManifestParseResult,
    WorkflowManifestReference,
    WorkflowManifestV2,
    WorkflowManifestV2FanoutNode,
    WorkflowManifestV2LoopNode,
    WorkflowManifestV2Node,
    WorkflowManifestV2Reference,
    WorkflowManifestV2SequenceNode,
    WorkflowManifestV2StepNode,
)

_PathToken = str | int

_ALLOWED_YAML_TAGS = {
    None,
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:seq",
    "tag:yaml.org,2002:str",
}


def parse_workflow_manifest(source: str) -> WorkflowManifestParseResult:
    return WorkflowManifestParser().parse(source)


def locate_workflow_manifest_path(source: str, path: str) -> tuple[int | None, int | None]:
    return WorkflowManifestParser().locate_path(source, path)


class WorkflowManifestParser:
    def parse(self, source: str) -> WorkflowManifestParseResult:
        syntax_diagnostics = self._scan_yaml_events(source)
        if syntax_diagnostics:
            return WorkflowManifestParseResult(diagnostics=syntax_diagnostics)

        try:
            data = self._new_yaml().load(source)
        except DuplicateKeyError as exc:
            return WorkflowManifestParseResult(diagnostics=[self._duplicate_key_diagnostic(exc)])
        except MarkedYAMLError as exc:
            return WorkflowManifestParseResult(diagnostics=[self._marked_yaml_diagnostic(exc)])
        except YAMLError as exc:
            return WorkflowManifestParseResult(
                diagnostics=[self._diagnostic(f"Malformed YAML: {exc}", path="$")]
            )

        if not isinstance(data, Mapping):
            return WorkflowManifestParseResult(
                diagnostics=[
                    self._diagnostic(
                        "Manifest source must be a YAML mapping",
                        path="$",
                        location=self._location_for(data, ()),
                    )
                ]
            )

        json_diagnostics = self._validate_json_compatible(data, ())
        if json_diagnostics:
            return WorkflowManifestParseResult(diagnostics=json_diagnostics)

        api_version = data.get("apiVersion")
        if api_version == WORKFLOW_MANIFEST_V1_API_VERSION:
            return self._parse_v1_manifest(data)
        if api_version == WORKFLOW_MANIFEST_V2_API_VERSION:
            if "steps" in data and "flow" not in data:
                return WorkflowManifestParseResult(
                    diagnostics=[
                        self._diagnostic(
                            f"Input should be '{WORKFLOW_MANIFEST_V1_API_VERSION}'",
                            path="apiVersion",
                            location=self._location_for(data, ("apiVersion",)),
                        )
                    ]
                )
            return self._parse_v2_manifest(data)
        return WorkflowManifestParseResult(
            diagnostics=[
                self._diagnostic(
                    self._api_version_message(api_version),
                    path="apiVersion",
                    location=self._location_for(data, ("apiVersion",)),
                )
            ]
        )

    def locate_path(self, source: str, path: str) -> tuple[int | None, int | None]:
        try:
            data = self._new_yaml().load(source)
        except YAMLError:
            return None, None
        return self._location_for(data, self._path_to_tokens(path))

    def _parse_v1_manifest(self, data: Mapping[object, object]) -> WorkflowManifestParseResult:
        try:
            manifest = WorkflowManifest.model_validate(data)
        except ValidationError as exc:
            return WorkflowManifestParseResult(diagnostics=self._validation_diagnostics(exc, data))

        semantic_diagnostics = self._validate_manifest_semantics(manifest, data)
        if semantic_diagnostics:
            return WorkflowManifestParseResult(diagnostics=semantic_diagnostics)
        return WorkflowManifestParseResult(manifest=manifest, diagnostics=[])

    def _parse_v2_manifest(self, data: Mapping[object, object]) -> WorkflowManifestParseResult:
        try:
            manifest = WorkflowManifestV2.model_validate(data)
        except ValidationError as exc:
            return WorkflowManifestParseResult(diagnostics=self._validation_diagnostics(exc, data))

        semantic_diagnostics = self._validate_v2_manifest_semantics(manifest, data)
        if semantic_diagnostics:
            return WorkflowManifestParseResult(diagnostics=semantic_diagnostics)
        return WorkflowManifestParseResult(manifest=manifest, diagnostics=[])

    def _scan_yaml_events(self, source: str) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        try:
            for event in self._new_yaml().parse(source):
                anchor = getattr(event, "anchor", None)
                if isinstance(event, AliasEvent):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML aliases are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                    continue
                if anchor:
                    diagnostics.append(
                        self._diagnostic(
                            "YAML anchors are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                tag = getattr(event, "tag", None)
                if tag == "tag:yaml.org,2002:merge":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif tag not in _ALLOWED_YAML_TAGS:
                    diagnostics.append(
                        self._diagnostic(
                            f"YAML tag {tag!r} is not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif isinstance(event, ScalarEvent) and event.value == "<<":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
        except DuplicateKeyError as exc:
            return [self._duplicate_key_diagnostic(exc)]
        except MarkedYAMLError as exc:
            return [self._marked_yaml_diagnostic(exc)]
        except YAMLError as exc:
            return [self._diagnostic(f"Malformed YAML: {exc}", path="$")]
        return diagnostics

    def _validate_json_compatible(
        self,
        value: object,
        tokens: tuple[_PathToken, ...],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        if isinstance(value, Mapping):
            mapping = cast(Mapping[object, object], value)
            for key, child in mapping.items():
                if not isinstance(key, str):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML mapping keys must be strings",
                            path=self._manifest_path(tokens),
                            location=self._location_for(value, tokens),
                        )
                    )
                    continue
                diagnostics.extend(self._validate_json_compatible(child, (*tokens, key)))
            return diagnostics
        if isinstance(value, bool | str) or value is None:
            return diagnostics
        if isinstance(value, int):
            return diagnostics
        if isinstance(value, float):
            if math.isfinite(value):
                return diagnostics
            diagnostics.append(
                self._diagnostic(
                    "YAML numeric values must be finite",
                    path=self._manifest_path(tokens),
                    location=self._location_for(value, tokens),
                )
            )
            return diagnostics
        if isinstance(value, Sequence):
            sequence = value
            for index, child in enumerate(sequence):
                diagnostics.extend(self._validate_json_compatible(child, (*tokens, index)))
            return diagnostics
        diagnostics.append(
            self._diagnostic(
                f"YAML value type {type(value).__name__!r} is not supported",
                path=self._manifest_path(tokens),
                location=self._location_for(value, tokens),
            )
        )
        return diagnostics

    def _validation_diagnostics(
        self,
        exc: ValidationError,
        data: object,
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        for raw_error in cast(list[object], exc.errors()):
            error = cast(Mapping[str, object], raw_error)
            tokens = self._error_loc_to_tokens(error.get("loc", ()))
            diagnostics.append(
                self._diagnostic(
                    self._clean_validation_message(str(error.get("msg", "Invalid manifest value"))),
                    path=self._manifest_path(tokens),
                    location=self._location_for(data, tokens),
                )
            )
        return diagnostics

    def _validate_manifest_semantics(
        self,
        manifest: WorkflowManifest,
        data: object,
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        step_index_by_id: dict[str, int] = {}
        slot_optional_by_step: dict[str, dict[str, bool]] = {}

        for step_index, step in enumerate(manifest.steps):
            step_path = ("steps", step_index, "id")
            if step.id in step_index_by_id:
                diagnostics.append(
                    self._diagnostic(
                        f"Duplicate step id: {step.id}",
                        path=self._manifest_path(step_path),
                        location=self._location_for(data, step_path),
                    )
                )
                continue
            step_index_by_id[step.id] = step_index

            slots: dict[str, bool] = {}
            for agent_index, agent in enumerate(step.agents):
                slot_path = ("steps", step_index, "agents", agent_index, "slot")
                if agent.slot in slots:
                    diagnostics.append(
                        self._diagnostic(
                            "Duplicate slot name within the same step",
                            path=self._manifest_path(slot_path),
                            location=self._location_for(data, slot_path),
                        )
                    )
                    continue
                slots[agent.slot] = agent.optional
            slot_optional_by_step[step.id] = slots

        if diagnostics:
            return diagnostics

        for step_index, step in enumerate(manifest.steps):
            for agent_index, agent in enumerate(step.agents):
                for field_name, reference in agent.inputs.items():
                    reference_path = (
                        "steps",
                        step_index,
                        "agents",
                        agent_index,
                        "with",
                        field_name,
                    )
                    diagnostic = self._validate_step_reference(
                        reference,
                        step_index=step_index,
                        step_index_by_id=step_index_by_id,
                        slot_optional_by_step=slot_optional_by_step,
                        path=reference_path,
                        data=data,
                    )
                    if diagnostic is not None:
                        diagnostics.append(diagnostic)

        output_reference = manifest.output.from_
        output_path = ("output", "from")
        output_diagnostic = self._validate_step_reference(
            output_reference,
            step_index=len(manifest.steps),
            step_index_by_id=step_index_by_id,
            slot_optional_by_step=slot_optional_by_step,
            path=output_path,
            data=data,
            forbid_optional=True,
        )
        if output_diagnostic is not None:
            diagnostics.append(output_diagnostic)
        return diagnostics

    def _validate_step_reference(
        self,
        reference: WorkflowManifestReference,
        *,
        step_index: int,
        step_index_by_id: dict[str, int],
        slot_optional_by_step: dict[str, dict[str, bool]],
        path: tuple[_PathToken, ...],
        data: object,
        forbid_optional: bool = False,
    ) -> WorkflowManifestDiagnostic | None:
        if reference.source != "steps":
            return None
        referenced_step_id = str(reference.step_id or "")
        referenced_slot = str(reference.slot or "")
        referenced_index = step_index_by_id.get(referenced_step_id)
        if referenced_index is None:
            return self._diagnostic(
                f"Step {referenced_step_id!r} was not found",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if referenced_index >= step_index:
            return self._diagnostic(
                "Step references must point to an earlier step",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        slots = slot_optional_by_step[referenced_step_id]
        if referenced_slot not in slots:
            return self._diagnostic(
                f"Slot {referenced_slot!r} was not found on step {referenced_step_id!r}",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if forbid_optional and slots[referenced_slot]:
            return self._diagnostic(
                "Final output cannot reference an optional slot",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        return None

    def _validate_v2_manifest_semantics(
        self,
        manifest: WorkflowManifestV2,
        data: object,
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        declarations = self._collect_v2_node_declarations(manifest.flow, ("flow",), data)
        diagnostics.extend(cast(list[WorkflowManifestDiagnostic], declarations["diagnostics"]))
        all_node_ids = cast(dict[str, tuple[_PathToken, ...]], declarations["node_paths"])

        if diagnostics:
            return diagnostics

        available_outputs: dict[str, dict[str, bool]] = {}
        diagnostics.extend(
            self._validate_v2_node_order(
                manifest.flow,
                node_path=("flow",),
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        )
        output_diagnostic = self._validate_v2_reference(
            manifest.output.from_,
            path=("output", "from"),
            data=data,
            available_outputs=available_outputs,
            all_node_ids=all_node_ids,
            forbid_optional=True,
        )
        if output_diagnostic is not None:
            diagnostics.append(output_diagnostic)
        diagnostics.extend(
            self._validate_v2_post_run_memory(
                manifest,
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        )
        return diagnostics

    def _collect_v2_node_declarations(
        self,
        node: WorkflowManifestV2Node,
        path: tuple[_PathToken, ...],
        data: object,
    ) -> dict[str, object]:
        node_paths: dict[str, tuple[_PathToken, ...]] = {}
        diagnostics: list[WorkflowManifestDiagnostic] = []

        def visit(current: WorkflowManifestV2Node, current_path: tuple[_PathToken, ...]) -> None:
            id_path = (*current_path, "id")
            if current.id in node_paths:
                diagnostics.append(
                    self._diagnostic(
                        f"Duplicate node id: {current.id}",
                        path=self._manifest_path(id_path),
                        location=self._location_for(data, id_path),
                    )
                )
            else:
                node_paths[current.id] = id_path

            if isinstance(current, WorkflowManifestV2SequenceNode):
                self._collect_v2_sequence_declarations(
                    current,
                    current_path,
                    visit,
                    diagnostics,
                    data,
                )
            elif isinstance(current, WorkflowManifestV2FanoutNode):
                self._collect_v2_fanout_declarations(
                    current,
                    current_path,
                    visit,
                    diagnostics,
                    data,
                )
            elif isinstance(current, WorkflowManifestV2LoopNode):
                visit(current.sequence, (*current_path, "sequence"))

        visit(node, path)
        return {"node_paths": node_paths, "diagnostics": diagnostics}

    def _collect_v2_sequence_declarations(
        self,
        sequence: WorkflowManifestV2SequenceNode,
        path: tuple[_PathToken, ...],
        visit: Callable[[WorkflowManifestV2Node, tuple[_PathToken, ...]], None],
        diagnostics: list[WorkflowManifestDiagnostic],
        data: object,
    ) -> None:
        output_slots: set[str] = set()
        for node_index, child in enumerate(sequence.nodes):
            child_path = (*path, "nodes", node_index)
            if isinstance(child, WorkflowManifestV2StepNode):
                slot_path = (*child_path, "slot")
                if child.slot in output_slots:
                    diagnostics.append(
                        self._diagnostic(
                            "Duplicate output slot name within the same sequence",
                            path=self._manifest_path(slot_path),
                            location=self._location_for(data, slot_path),
                        )
                    )
                output_slots.add(child.slot)
            visit(child, child_path)

    def _collect_v2_fanout_declarations(
        self,
        fanout: WorkflowManifestV2FanoutNode,
        path: tuple[_PathToken, ...],
        visit: Callable[[WorkflowManifestV2Node, tuple[_PathToken, ...]], None],
        diagnostics: list[WorkflowManifestDiagnostic],
        data: object,
    ) -> None:
        branch_ids: set[str] = set()
        output_slots: set[str] = set()
        for branch_index, branch in enumerate(fanout.branches):
            branch_path = (*path, "branches", branch_index)
            branch_id_path = (*branch_path, "id")
            if branch.id in branch_ids:
                diagnostics.append(
                    self._diagnostic(
                        f"Duplicate fanout branch id: {branch.id}",
                        path=self._manifest_path(branch_id_path),
                        location=self._location_for(data, branch_id_path),
                    )
                )
            branch_ids.add(branch.id)
            if isinstance(branch.node, WorkflowManifestV2StepNode):
                slot_path = (*branch_path, "node", "slot")
                if branch.node.slot in output_slots:
                    diagnostics.append(
                        self._diagnostic(
                            "Duplicate output slot name within the same fanout",
                            path=self._manifest_path(slot_path),
                            location=self._location_for(data, slot_path),
                        )
                    )
                output_slots.add(branch.node.slot)
            visit(branch.node, (*branch_path, "node"))

    def _validate_v2_node_order(
        self,
        node: WorkflowManifestV2Node,
        *,
        node_path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        if isinstance(node, WorkflowManifestV2StepNode):
            return self._validate_v2_step_node(
                node,
                node_path=node_path,
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        if isinstance(node, WorkflowManifestV2SequenceNode):
            return self._validate_v2_sequence_node(
                node,
                node_path=node_path,
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        if isinstance(node, WorkflowManifestV2FanoutNode):
            return self._validate_v2_fanout_node(
                node,
                node_path=node_path,
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        return self._validate_v2_loop_node(
            node,
            node_path=node_path,
            data=data,
            available_outputs=available_outputs,
            all_node_ids=all_node_ids,
        )

    def _validate_v2_step_node(
        self,
        node: WorkflowManifestV2StepNode,
        *,
        node_path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        for field_name, reference in node.inputs.items():
            diagnostic = self._validate_v2_reference(
                reference,
                path=(*node_path, "with", field_name),
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        available_outputs[node.id] = {node.slot: node.optional}
        return diagnostics

    def _validate_v2_sequence_node(
        self,
        node: WorkflowManifestV2SequenceNode,
        *,
        node_path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        local_outputs: dict[str, bool] = {}
        for node_index, child in enumerate(node.nodes):
            diagnostics.extend(
                self._validate_v2_node_order(
                    child,
                    node_path=(*node_path, "nodes", node_index),
                    data=data,
                    available_outputs=available_outputs,
                    all_node_ids=all_node_ids,
                )
            )
            local_outputs.update(self._v2_node_outputs(child, available_outputs))
        available_outputs[node.id] = local_outputs
        return diagnostics

    def _validate_v2_fanout_node(
        self,
        node: WorkflowManifestV2FanoutNode,
        *,
        node_path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        fanout_outputs: dict[str, bool] = {}
        pre_fanout_outputs = {node_id: dict(slots) for node_id, slots in available_outputs.items()}
        branch_available_outputs: dict[str, dict[str, bool]] = {}
        for branch_index, branch in enumerate(node.branches):
            branch_outputs = {node_id: dict(slots) for node_id, slots in pre_fanout_outputs.items()}
            diagnostics.extend(
                self._validate_v2_node_order(
                    branch.node,
                    node_path=(*node_path, "branches", branch_index, "node"),
                    data=data,
                    available_outputs=branch_outputs,
                    all_node_ids=all_node_ids,
                )
            )
            branch_node_outputs = self._v2_node_outputs(branch.node, branch_outputs)
            if branch_node_outputs:
                fanout_outputs[branch.id] = any(branch_node_outputs.values())
                for slot, optional in branch_node_outputs.items():
                    _ = fanout_outputs.setdefault(slot, optional)
            for node_id, slots in branch_outputs.items():
                if node_id not in pre_fanout_outputs:
                    branch_available_outputs[node_id] = slots
        available_outputs.update(branch_available_outputs)
        available_outputs[node.id] = fanout_outputs
        return diagnostics

    def _validate_v2_loop_node(
        self,
        node: WorkflowManifestV2LoopNode,
        *,
        node_path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        for field_name, reference in node.state.items():
            diagnostic = self._validate_v2_reference(
                reference,
                path=(*node_path, "state", field_name),
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        diagnostics.extend(
            self._validate_v2_node_order(
                node.sequence,
                node_path=(*node_path, "sequence"),
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
        )
        available_outputs[node.id] = self._v2_node_outputs(node.sequence, available_outputs)
        return diagnostics

    def _validate_v2_post_run_memory(
        self,
        manifest: WorkflowManifestV2,
        *,
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        memory = manifest.post_run_memory
        if memory.source is not None:
            source_refs = {
                "ticker": memory.source.ticker,
                "action": memory.source.action,
                "rationale": memory.source.rationale,
                "risk_summary": memory.source.risk_summary,
                "execution_plan": memory.source.execution_plan,
                "portfolio_slug": memory.source.portfolio_slug,
                "horizon_days": memory.source.horizon_days,
                "confidence": memory.source.confidence,
                "decision_summary": memory.source.decision_summary,
            }
            for field_name, reference in source_refs.items():
                if reference is None:
                    continue
                diagnostic = self._validate_v2_reference(
                    reference,
                    path=("postRunMemory", "source", self._v2_memory_source_alias(field_name)),
                    data=data,
                    available_outputs=available_outputs,
                    all_node_ids=all_node_ids,
                )
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
        if memory.benchmark_symbol is not None:
            diagnostic = self._validate_v2_reference(
                memory.benchmark_symbol,
                path=("postRunMemory", "benchmarkSymbol"),
                data=data,
                available_outputs=available_outputs,
                all_node_ids=all_node_ids,
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        return diagnostics

    def _validate_v2_reference(
        self,
        reference: WorkflowManifestV2Reference,
        *,
        path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, dict[str, bool]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
        forbid_optional: bool = False,
    ) -> WorkflowManifestDiagnostic | None:
        if reference.source != "nodes":
            return None
        referenced_node_id = str(reference.node_id or "")
        referenced_slot = str(reference.slot or "")
        slots = available_outputs.get(referenced_node_id)
        if slots is None:
            if referenced_node_id in all_node_ids:
                return self._diagnostic(
                    "Node references must point to an earlier node",
                    path=self._manifest_path(path),
                    location=self._location_for(data, path),
                )
            return self._diagnostic(
                f"Node {referenced_node_id!r} was not found",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if referenced_slot not in slots:
            return self._diagnostic(
                f"Slot {referenced_slot!r} was not found on node {referenced_node_id!r}",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if forbid_optional and slots[referenced_slot]:
            return self._diagnostic(
                "Final output cannot reference an optional slot",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        return None

    @staticmethod
    def _v2_node_outputs(
        node: WorkflowManifestV2Node,
        available_outputs: dict[str, dict[str, bool]],
    ) -> dict[str, bool]:
        return dict(available_outputs.get(node.id, {}))

    @staticmethod
    def _v2_memory_source_alias(field_name: str) -> str:
        aliases = {
            "risk_summary": "riskSummary",
            "execution_plan": "executionPlan",
            "portfolio_slug": "portfolioSlug",
            "horizon_days": "horizonDays",
            "decision_summary": "decisionSummary",
        }
        return aliases.get(field_name, field_name)

    @staticmethod
    def _new_yaml() -> YAML:
        yaml = YAML(typ="rt")
        yaml.allow_duplicate_keys = False
        yaml.version = (1, 2)
        return yaml

    def _duplicate_key_diagnostic(self, exc: DuplicateKeyError) -> WorkflowManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        return self._diagnostic(
            "Duplicate mapping key is not allowed",
            path="$",
            location=self._mark_location(mark),
        )

    def _marked_yaml_diagnostic(self, exc: MarkedYAMLError) -> WorkflowManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        return self._diagnostic(
            f"Malformed YAML: {problem}",
            path="$",
            location=self._mark_location(mark),
        )

    @staticmethod
    def _api_version_message(api_version: object) -> str:
        if api_version is None:
            return "Field required"
        return (
            "Input should be "
            f"'{WORKFLOW_MANIFEST_V1_API_VERSION}' or '{WORKFLOW_MANIFEST_V2_API_VERSION}'"
        )

    @staticmethod
    def _diagnostic(
        message: str,
        *,
        path: str,
        location: tuple[int | None, int | None] = (None, None),
    ) -> WorkflowManifestDiagnostic:
        line, column = location
        return WorkflowManifestDiagnostic(
            severity=WorkflowManifestDiagnosticSeverity.ERROR,
            message=message,
            path=path,
            line=line,
            column=column,
        )

    @staticmethod
    def _clean_validation_message(message: str) -> str:
        return message.removeprefix("Value error, ")

    @staticmethod
    def _error_loc_to_tokens(loc: object) -> tuple[_PathToken, ...]:
        if not isinstance(loc, Iterable) or isinstance(loc, str | bytes):
            return ()
        aliases = {
            "from_": "from",
            "input_schema": "inputSchema",
            "api_version": "apiVersion",
            "post_run_memory": "postRunMemory",
            "max_iterations": "maxIterations",
            "benchmark_symbol": "benchmarkSymbol",
            "risk_summary": "riskSummary",
            "execution_plan": "executionPlan",
            "portfolio_slug": "portfolioSlug",
            "horizon_days": "horizonDays",
            "decision_summary": "decisionSummary",
        }
        tokens: list[_PathToken] = []
        for item in loc:
            if isinstance(item, str):
                tokens.append(aliases.get(item, item))
            elif isinstance(item, int):
                tokens.append(item)
        return tuple(tokens)

    @staticmethod
    def _manifest_path(tokens: tuple[_PathToken, ...]) -> str:
        if not tokens:
            return "$"
        path = ""
        for token in tokens:
            if isinstance(token, int):
                path += f"[{token}]"
            elif not path:
                path = token
            else:
                path += f".{token}"
        return path

    @staticmethod
    def _path_to_tokens(path: str) -> tuple[_PathToken, ...]:
        if path == "$":
            return ()
        tokens: list[_PathToken] = []
        for raw_segment in path.split("."):
            segment = raw_segment
            while segment:
                key_match = re.match(r"[^\[\]]+", segment)
                if key_match is not None:
                    tokens.append(key_match.group(0))
                    segment = segment[key_match.end() :]
                    continue
                index_match = re.match(r"\[(\d+)\]", segment)
                if index_match is None:
                    return ()
                tokens.append(int(index_match.group(1)))
                segment = segment[index_match.end() :]
        return tuple(tokens)

    def _location_for(
        self,
        root: object,
        tokens: tuple[_PathToken, ...],
    ) -> tuple[int | None, int | None]:
        current = root
        last_location = self._object_location(root)
        for index, token in enumerate(tokens):
            if isinstance(current, Mapping) and isinstance(token, str):
                mapping = cast(Mapping[object, object], current)
                if token not in mapping:
                    return last_location
                location = self._map_value_location(current, token)
                if index == len(tokens) - 1:
                    return location
                last_location = location
                current = mapping[token]
                continue
            if (
                isinstance(current, Sequence)
                and not isinstance(current, str | bytes)
                and isinstance(token, int)
            ):
                sequence = cast(Sequence[object], current)
                if token < 0 or token >= len(sequence):
                    return last_location
                location = self._sequence_item_location(current, token)
                if index == len(tokens) - 1:
                    return location
                last_location = location
                current = sequence[token]
                continue
            return last_location
        return last_location

    @staticmethod
    def _object_location(value: object) -> tuple[int | None, int | None]:
        lc = getattr(value, "lc", None)
        line = getattr(lc, "line", None)
        column = getattr(lc, "col", None)
        if isinstance(line, int) and isinstance(column, int):
            return line + 1, column + 1
        return None, None

    def _map_value_location(
        self,
        mapping: object,
        key: str,
    ) -> tuple[int | None, int | None]:
        lc = getattr(mapping, "lc", None)
        for accessor_name in ("value", "key"):
            accessor = getattr(lc, accessor_name, None)
            if accessor is None:
                continue
            accessor_fn = cast(Callable[[str], object], accessor)
            try:
                raw_location = accessor_fn(key)
            except (KeyError, TypeError):
                continue
            location = self._raw_location(raw_location)
            if location != (None, None):
                return location
        return self._object_location(mapping)

    def _sequence_item_location(
        self,
        sequence: object,
        index: int,
    ) -> tuple[int | None, int | None]:
        lc = getattr(sequence, "lc", None)
        item = getattr(lc, "item", None)
        if item is not None:
            item_fn = cast(Callable[[int], object], item)
            try:
                raw_location = item_fn(index)
                location = self._raw_location(raw_location)
            except (KeyError, TypeError):
                location = (None, None)
            if location != (None, None):
                return location
        return self._object_location(sequence)

    @staticmethod
    def _raw_location(raw_location: object) -> tuple[int | None, int | None]:
        if (
            isinstance(raw_location, tuple)
            and len(raw_location) >= 2
            and isinstance(raw_location[0], int)
            and isinstance(raw_location[1], int)
        ):
            return raw_location[0] + 1, raw_location[1] + 1
        return None, None

    @staticmethod
    def _mark_location(mark: object) -> tuple[int | None, int | None]:
        line = getattr(mark, "line", None)
        column = getattr(mark, "column", None)
        if isinstance(line, int) and isinstance(column, int):
            return line + 1, column + 1
        return None, None


__all__ = [
    "WorkflowManifestParser",
    "locate_workflow_manifest_path",
    "parse_workflow_manifest",
]
