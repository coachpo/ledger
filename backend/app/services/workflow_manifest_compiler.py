from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import cast

from app.repositories.output_schema import OutputSchemaRepository
from app.schemas.workflow import WorkflowCreate
from app.schemas.workflow_manifest import (
    WORKFLOW_MANIFEST_V2_MAX_FANOUT_BRANCHES,
    WORKFLOW_MANIFEST_V2_MAX_LOOP_ITERATIONS,
    WorkflowManifest,
    WorkflowManifestDiagnostic,
    WorkflowManifestDiagnosticSeverity,
    WorkflowManifestDocument,
    WorkflowManifestReference,
    WorkflowManifestV2,
    WorkflowManifestV2FanoutNode,
    WorkflowManifestV2LoopNode,
    WorkflowManifestV2Node,
    WorkflowManifestV2Reference,
    WorkflowManifestV2SequenceNode,
    WorkflowManifestV2StepNode,
)
from app.services.output_schema_compiler import OutputSchemaCompiler, OutputSchemaValidationFailure
from app.services.workflow_manifest_parser import (
    locate_workflow_manifest_path,
    parse_workflow_manifest,
)


class WorkflowManifestCompilerError(ValueError):
    def __init__(self, diagnostics: list[WorkflowManifestDiagnostic]) -> None:
        super().__init__("Workflow manifest could not be compiled")
        self.diagnostics: list[WorkflowManifestDiagnostic] = diagnostics


class _UnavailableOutputSchemaRepository:
    def resolve_registry_ref(self, _key: str, _version: int | None) -> None:
        return None


@dataclass(frozen=True)
class _CompiledOutputRef:
    step_index: int
    slot: str
    source_node_id: str
    source_slot: str


@dataclass(frozen=True)
class _CompiledStateRef:
    output_ref: _CompiledOutputRef
    output_path: str | None = None


@dataclass
class _CompiledStepDraft:
    index: int
    agents: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _V2CompilerContext:
    output_ref_by_node_slot: dict[str, dict[str, _CompiledOutputRef]] = field(default_factory=dict)
    step_drafts: list[_CompiledStepDraft] = field(default_factory=list)
    graph_nodes: list[dict[str, object]] = field(default_factory=list)

    def create_step(self) -> _CompiledStepDraft:
        step = _CompiledStepDraft(index=len(self.step_drafts) + 1)
        self.step_drafts.append(step)
        return step

    def register_output(
        self,
        *,
        node_id: str,
        slot: str,
        ref: _CompiledOutputRef,
    ) -> None:
        self.output_ref_by_node_slot.setdefault(node_id, {})[slot] = ref

    def node_outputs(self, node_id: str) -> dict[str, _CompiledOutputRef]:
        return dict(self.output_ref_by_node_slot.get(node_id, {}))


def compile_workflow_manifest(
    source: str | WorkflowManifestDocument,
    *,
    schema_compiler: OutputSchemaCompiler | None = None,
) -> dict[str, object]:
    manifest, source_text = _resolve_manifest(source)
    input_schema = _normalize_input_schema(
        manifest.input_schema,
        source=source_text,
        schema_compiler=schema_compiler,
    )
    if isinstance(manifest, WorkflowManifest):
        return _compile_v1_manifest(manifest, input_schema)
    return _compile_v2_manifest(manifest, input_schema)


def _compile_v1_manifest(
    manifest: WorkflowManifest,
    input_schema: dict[str, object],
) -> dict[str, object]:
    step_index_by_id = {step.id: index for index, step in enumerate(manifest.steps, start=1)}
    payload: dict[str, object] = {
        "key": manifest.metadata.key,
        "name": manifest.metadata.name,
        "description": manifest.metadata.description,
        "inputSchema": input_schema,
        "steps": [
            {
                "index": step_index,
                "agents": [
                    {
                        "agentKey": agent.uses.key,
                        "agentVersion": agent.uses.version,
                        "slot": agent.slot,
                        "wiring": {
                            field_name: _compile_reference(reference, step_index_by_id)
                            for field_name, reference in agent.inputs.items()
                        },
                        "optional": agent.optional,
                    }
                    for agent in step.agents
                ],
            }
            for step_index, step in enumerate(manifest.steps, start=1)
        ],
        "outputSpec": _compile_output_spec(manifest.output.from_, step_index_by_id),
    }
    return _validate_workflow_create_payload(payload)


def _compile_v2_manifest(
    manifest: WorkflowManifestV2,
    input_schema: dict[str, object],
) -> dict[str, object]:
    context = _V2CompilerContext()
    _ = _compile_v2_node(manifest.flow, context=context, graph_path=manifest.flow.id)
    core_payload: dict[str, object] = {
        "key": manifest.metadata.key,
        "name": manifest.metadata.name,
        "description": manifest.metadata.description,
        "inputSchema": input_schema,
        "steps": [{"index": step.index, "agents": step.agents} for step in context.step_drafts],
        "outputSpec": _compile_v2_output_spec(manifest.output.from_, context),
    }
    payload = _validate_workflow_create_payload(core_payload)
    payload["compiledGraph"] = _compile_v2_graph(manifest, context)
    return payload


def _validate_workflow_create_payload(payload: dict[str, object]) -> dict[str, object]:
    return cast(
        dict[str, object],
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
    )


def _compile_v2_node(
    node: WorkflowManifestV2Node,
    *,
    context: _V2CompilerContext,
    graph_path: str,
    loop_id: str | None = None,
    loop_iteration: int | None = None,
    branch_id: str | None = None,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, _CompiledOutputRef]:
    if isinstance(node, WorkflowManifestV2StepNode):
        return _compile_v2_step_node(
            node,
            context=context,
            graph_path=graph_path,
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            branch_id=branch_id,
            state_refs=state_refs,
        )
    if isinstance(node, WorkflowManifestV2SequenceNode):
        return _compile_v2_sequence_node(
            node,
            context=context,
            graph_path=graph_path,
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            branch_id=branch_id,
            state_refs=state_refs,
        )
    if isinstance(node, WorkflowManifestV2FanoutNode):
        return _compile_v2_fanout_node(
            node,
            context=context,
            graph_path=graph_path,
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            branch_id=branch_id,
            state_refs=state_refs,
        )
    return _compile_v2_loop_node(
        node,
        context=context,
        graph_path=graph_path,
        loop_id=loop_id,
        loop_iteration=loop_iteration,
        branch_id=branch_id,
        state_refs=state_refs,
    )


def _compile_v2_step_node(
    node: WorkflowManifestV2StepNode,
    *,
    context: _V2CompilerContext,
    graph_path: str,
    loop_id: str | None,
    loop_iteration: int | None,
    branch_id: str | None,
    step: _CompiledStepDraft | None = None,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, _CompiledOutputRef]:
    step_draft = step or context.create_step()
    wiring = {
        field_name: _compile_v2_reference(reference, context, state_refs=state_refs)
        for field_name, reference in node.inputs.items()
    }
    agent: dict[str, object] = {
        "agentKey": node.uses.key,
        "agentVersion": node.uses.version,
        "slot": node.slot,
        "wiring": wiring,
        "optional": node.optional,
    }
    step_draft.agents.append(agent)
    output_ref = _CompiledOutputRef(
        step_index=step_draft.index,
        slot=node.slot,
        source_node_id=node.id,
        source_slot=node.slot,
    )
    context.register_output(node_id=node.id, slot=node.slot, ref=output_ref)
    context.graph_nodes.append(
        _without_none(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "step",
                "stepIndex": step_draft.index,
                "slot": node.slot,
                "agentKey": node.uses.key,
                "agentVersion": node.uses.version,
                "optional": node.optional,
                "refs": _compile_v2_graph_refs(node.inputs, context, state_refs=state_refs),
                "branchId": branch_id,
                "loopId": loop_id,
                "loopIteration": loop_iteration,
            }
        )
    )
    return {node.slot: output_ref}


def _compile_v2_sequence_node(
    node: WorkflowManifestV2SequenceNode,
    *,
    context: _V2CompilerContext,
    graph_path: str,
    loop_id: str | None,
    loop_iteration: int | None,
    branch_id: str | None,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, _CompiledOutputRef]:
    outputs: dict[str, _CompiledOutputRef] = {}
    context.graph_nodes.append(
        _without_none(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "sequence",
                "childNodeIds": [child.id for child in node.nodes],
                "branchId": branch_id,
                "loopId": loop_id,
                "loopIteration": loop_iteration,
            }
        )
    )
    for child in node.nodes:
        child_outputs = _compile_v2_node(
            child,
            context=context,
            graph_path=f"{graph_path}.{child.id}",
            loop_id=loop_id,
            loop_iteration=loop_iteration,
            branch_id=branch_id,
            state_refs=state_refs,
        )
        outputs.update(child_outputs)
    for slot, ref in outputs.items():
        context.register_output(node_id=node.id, slot=slot, ref=ref)
    return outputs


def _compile_v2_fanout_node(
    node: WorkflowManifestV2FanoutNode,
    *,
    context: _V2CompilerContext,
    graph_path: str,
    loop_id: str | None,
    loop_iteration: int | None,
    branch_id: str | None,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, _CompiledOutputRef]:
    outputs: dict[str, _CompiledOutputRef] = {}
    simple_step_branches = all(
        isinstance(branch.node, WorkflowManifestV2StepNode) for branch in node.branches
    )
    context.graph_nodes.append(
        _without_none(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "fanout",
                "branchIds": [branch.id for branch in node.branches],
                "mode": "concurrent" if simple_step_branches else "expanded",
                "branchId": branch_id,
                "loopId": loop_id,
                "loopIteration": loop_iteration,
            }
        )
    )

    pre_fanout_outputs = _copy_v2_output_refs(context.output_ref_by_node_slot)
    branch_output_refs: dict[str, dict[str, _CompiledOutputRef]] = {}
    if simple_step_branches:
        fanout_step = context.create_step()
        for branch in node.branches:
            context.output_ref_by_node_slot = _copy_v2_output_refs(pre_fanout_outputs)
            child = cast(WorkflowManifestV2StepNode, branch.node)
            branch_outputs = _compile_v2_step_node(
                child,
                context=context,
                graph_path=f"{graph_path}.{branch.id}.{child.id}",
                loop_id=loop_id,
                loop_iteration=loop_iteration,
                branch_id=branch.id,
                step=fanout_step,
                state_refs=state_refs,
            )
            outputs.update(branch_outputs)
            _register_v2_branch_aliases(
                node_id=node.id,
                branch_id=branch.id,
                branch_outputs=branch_outputs,
                context=context,
                outputs=outputs,
            )
            _capture_v2_branch_output_refs(
                context=context,
                baseline=pre_fanout_outputs,
                fanout_node_id=node.id,
                branch_output_refs=branch_output_refs,
            )
    else:
        for branch in node.branches:
            context.output_ref_by_node_slot = _copy_v2_output_refs(pre_fanout_outputs)
            branch_outputs = _compile_v2_node(
                branch.node,
                context=context,
                graph_path=f"{graph_path}.{branch.id}.{branch.node.id}",
                loop_id=loop_id,
                loop_iteration=loop_iteration,
                branch_id=branch.id,
                state_refs=state_refs,
            )
            outputs.update(branch_outputs)
            _register_v2_branch_aliases(
                node_id=node.id,
                branch_id=branch.id,
                branch_outputs=branch_outputs,
                context=context,
                outputs=outputs,
            )
            _capture_v2_branch_output_refs(
                context=context,
                baseline=pre_fanout_outputs,
                fanout_node_id=node.id,
                branch_output_refs=branch_output_refs,
            )
    context.output_ref_by_node_slot = _copy_v2_output_refs(pre_fanout_outputs)
    context.output_ref_by_node_slot.update(branch_output_refs)
    for slot, ref in outputs.items():
        context.register_output(node_id=node.id, slot=slot, ref=ref)
    return outputs


def _register_v2_branch_aliases(
    *,
    node_id: str,
    branch_id: str,
    branch_outputs: dict[str, _CompiledOutputRef],
    context: _V2CompilerContext,
    outputs: dict[str, _CompiledOutputRef],
) -> None:
    if not branch_outputs:
        return
    branch_ref = next(iter(branch_outputs.values()))
    outputs[branch_id] = branch_ref
    context.register_output(node_id=node_id, slot=branch_id, ref=branch_ref)


def _copy_v2_output_refs(
    refs: dict[str, dict[str, _CompiledOutputRef]],
) -> dict[str, dict[str, _CompiledOutputRef]]:
    return {node_id: dict(slots) for node_id, slots in refs.items()}


def _capture_v2_branch_output_refs(
    *,
    context: _V2CompilerContext,
    baseline: dict[str, dict[str, _CompiledOutputRef]],
    fanout_node_id: str,
    branch_output_refs: dict[str, dict[str, _CompiledOutputRef]],
) -> None:
    for node_id, slots in context.output_ref_by_node_slot.items():
        if node_id in baseline or node_id == fanout_node_id:
            continue
        branch_output_refs[node_id] = dict(slots)


def _compile_v2_loop_node(
    node: WorkflowManifestV2LoopNode,
    *,
    context: _V2CompilerContext,
    graph_path: str,
    loop_id: str | None,
    loop_iteration: int | None,
    branch_id: str | None,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, _CompiledOutputRef]:
    context.graph_nodes.append(
        _without_none(
            {
                "id": graph_path,
                "nodeId": node.id,
                "kind": "loop",
                "loopId": node.id,
                "maxIterations": node.max_iterations,
                "stateRefs": _compile_v2_graph_refs(node.state, context, state_refs=state_refs),
                "sequenceNodeId": node.sequence.id,
                "parentLoopId": loop_id,
                "parentLoopIteration": loop_iteration,
                "branchId": branch_id,
            }
        )
    )
    outputs: dict[str, _CompiledOutputRef] = {}
    iteration_state_refs: dict[str, _CompiledStateRef] | None = None
    for iteration_index in range(1, node.max_iterations + 1):
        outputs = _compile_v2_sequence_node(
            node.sequence,
            context=context,
            graph_path=f"{graph_path}.iteration_{iteration_index}.{node.sequence.id}",
            loop_id=node.id,
            loop_iteration=iteration_index,
            branch_id=branch_id,
            state_refs=iteration_state_refs,
        )
        iteration_state_refs = _compile_v2_next_loop_state_refs(node.state, outputs)
    for slot, ref in outputs.items():
        context.register_output(node_id=node.id, slot=slot, ref=ref)
    return outputs


def _compile_v2_next_loop_state_refs(
    state: dict[str, WorkflowManifestV2Reference],
    outputs: dict[str, _CompiledOutputRef],
) -> dict[str, _CompiledStateRef] | None:
    if not state or not outputs:
        return None
    fallback_slot = next(reversed(outputs)) if len(state) == 1 else None
    state_refs: dict[str, _CompiledStateRef] = {}
    for state_name, reference in state.items():
        selector = _resolve_v2_loop_state_selector(state_name, outputs, fallback_slot)
        if selector is None:
            continue
        output_ref, output_path = selector
        state_refs[reference.expression] = _CompiledStateRef(
            output_ref=output_ref,
            output_path=output_path,
        )
    return state_refs or None


def _resolve_v2_loop_state_selector(
    state_name: str,
    outputs: dict[str, _CompiledOutputRef],
    fallback_slot: str | None,
) -> tuple[_CompiledOutputRef, str | None] | None:
    if state_name in outputs:
        return outputs[state_name], None
    slot, separator, output_path = state_name.partition(".")
    if separator and slot in outputs and output_path:
        return outputs[slot], output_path
    if fallback_slot is not None:
        return outputs[fallback_slot], None
    return None


def _compile_v2_reference(
    reference: WorkflowManifestV2Reference,
    context: _V2CompilerContext,
    *,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, object]:
    state_ref = None if state_refs is None else state_refs.get(reference.expression)
    if state_ref is not None:
        return _compile_v2_state_ref_payload(state_ref)
    if reference.source == "inputs":
        if reference.path is None:
            raise ValueError("Input references must include a path")
        return {"from": "input", "path": reference.path}

    output_ref = _resolve_v2_output_ref(reference, context)
    payload = _compile_v2_output_ref_payload(output_ref)
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_v2_graph_refs(
    references: dict[str, WorkflowManifestV2Reference],
    context: _V2CompilerContext,
    *,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, object]:
    return {
        field_name: _compile_v2_graph_ref(reference, context, state_refs=state_refs)
        for field_name, reference in references.items()
    }


def _compile_v2_graph_ref(
    reference: WorkflowManifestV2Reference,
    context: _V2CompilerContext,
    *,
    state_refs: dict[str, _CompiledStateRef] | None = None,
) -> dict[str, object]:
    state_ref = None if state_refs is None else state_refs.get(reference.expression)
    if state_ref is not None:
        return _compile_v2_state_graph_ref(reference, state_ref)
    if reference.source == "inputs":
        if reference.path is None:
            raise ValueError("Input references must include a path")
        return {"source": "inputs", "path": reference.path}
    output_ref = _resolve_v2_output_ref(reference, context)
    payload = _compile_v2_output_graph_ref(reference, output_ref)
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_v2_output_ref_payload(output_ref: _CompiledOutputRef) -> dict[str, object]:
    return {
        "from": "step",
        "stepIndex": output_ref.step_index,
        "slot": output_ref.slot,
    }


def _compile_v2_state_ref_payload(state_ref: _CompiledStateRef) -> dict[str, object]:
    payload = _compile_v2_output_ref_payload(state_ref.output_ref)
    if state_ref.output_path is not None:
        payload["path"] = state_ref.output_path
    return payload


def _compile_v2_output_graph_ref(
    reference: WorkflowManifestV2Reference,
    output_ref: _CompiledOutputRef,
) -> dict[str, object]:
    return {
        "source": "nodes",
        "nodeId": reference.node_id or "",
        "slot": reference.slot or "",
        "stepIndex": output_ref.step_index,
        "compiledSlot": output_ref.slot,
        "sourceNodeId": output_ref.source_node_id,
        "sourceSlot": output_ref.source_slot,
    }


def _compile_v2_state_graph_ref(
    _reference: WorkflowManifestV2Reference,
    state_ref: _CompiledStateRef,
) -> dict[str, object]:
    output_ref = state_ref.output_ref
    payload: dict[str, object] = {
        "source": "nodes",
        "nodeId": output_ref.source_node_id,
        "slot": output_ref.source_slot,
        "stepIndex": output_ref.step_index,
        "compiledSlot": output_ref.slot,
        "sourceNodeId": output_ref.source_node_id,
        "sourceSlot": output_ref.source_slot,
    }
    if state_ref.output_path is not None:
        payload["path"] = state_ref.output_path
    return payload


def _compile_v2_output_spec(
    reference: WorkflowManifestV2Reference,
    context: _V2CompilerContext,
) -> dict[str, object]:
    output_ref = _resolve_v2_output_ref(reference, context)
    payload: dict[str, object] = {
        "kind": "slot",
        "stepIndex": output_ref.step_index,
        "slot": output_ref.slot,
    }
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_v2_graph(
    manifest: WorkflowManifestV2,
    context: _V2CompilerContext,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "apiVersion": manifest.api_version,
        "rootNodeId": manifest.flow.id,
        "nodes": context.graph_nodes,
        "output": _compile_v2_graph_ref(
            manifest.output.from_,
            context,
        ),
        "validation": {
            "inputSchemaType": manifest.input_schema.get("type"),
            "loopMaxIterations": WORKFLOW_MANIFEST_V2_MAX_LOOP_ITERATIONS,
            "fanoutMaxBranches": WORKFLOW_MANIFEST_V2_MAX_FANOUT_BRANCHES,
        },
    }
    post_run_memory = _compile_v2_post_run_memory(manifest, context)
    if post_run_memory is not None:
        payload["postRunMemory"] = post_run_memory
    return payload


def _compile_v2_post_run_memory(
    manifest: WorkflowManifestV2,
    context: _V2CompilerContext,
) -> dict[str, object] | None:
    memory = manifest.post_run_memory
    if not memory.enabled or memory.source is None:
        return None
    source_refs = {
        "ticker": memory.source.ticker,
        "action": memory.source.action,
        "rationale": memory.source.rationale,
        "riskSummary": memory.source.risk_summary,
        "executionPlan": memory.source.execution_plan,
        "portfolioSlug": memory.source.portfolio_slug,
        "horizonDays": memory.source.horizon_days,
        "confidence": memory.source.confidence,
        "decisionSummary": memory.source.decision_summary,
    }
    payload: dict[str, object] = {
        "enabled": True,
        "sourceRefs": {
            field_name: _compile_v2_graph_ref(reference, context)
            for field_name, reference in source_refs.items()
            if reference is not None
        },
    }
    if memory.benchmark_symbol is not None:
        payload["benchmarkSymbol"] = _compile_v2_graph_ref(
            memory.benchmark_symbol,
            context,
        )
    return payload


def _resolve_v2_output_ref(
    reference: WorkflowManifestV2Reference,
    context: _V2CompilerContext,
) -> _CompiledOutputRef:
    if reference.node_id is None:
        raise ValueError("Node output references must include a node id")
    if reference.slot is None:
        raise ValueError("Node output references must include a slot")
    return context.output_ref_by_node_slot[reference.node_id][reference.slot]


def _without_none(value: dict[str, object | None]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item is not None}


def _resolve_manifest(
    source: str | WorkflowManifestDocument,
) -> tuple[WorkflowManifestDocument, str | None]:
    if isinstance(source, WorkflowManifest | WorkflowManifestV2):
        return source, None

    result = parse_workflow_manifest(source)
    if result.manifest is None or result.diagnostics:
        raise WorkflowManifestCompilerError(result.diagnostics)
    return result.manifest, source


def _normalize_input_schema(
    input_schema: Mapping[str, object],
    *,
    source: str | None,
    schema_compiler: OutputSchemaCompiler | None,
) -> dict[str, object]:
    compiler = schema_compiler or OutputSchemaCompiler(
        cast(OutputSchemaRepository, cast(object, _UnavailableOutputSchemaRepository()))
    )
    try:
        prepared_schema = compiler.normalize_payload(
            builder=None,
            json_schema=dict(input_schema),
        )
    except OutputSchemaValidationFailure as exc:
        raise WorkflowManifestCompilerError(
            [
                _diagnostic(
                    issue.get("issue", "Invalid input schema"),
                    path=_input_schema_issue_path(issue.get("field", "jsonSchema")),
                    source=source,
                )
                for issue in exc.issues
            ]
        ) from exc
    return cast(dict[str, object], prepared_schema.json_schema)


def _input_schema_issue_path(field: str) -> str:
    if field == "jsonSchema":
        return "inputSchema"
    if field.startswith("jsonSchema."):
        return field.replace("jsonSchema", "inputSchema", 1)
    return f"inputSchema.{field}"


def _diagnostic(
    message: str,
    *,
    path: str,
    source: str | None,
) -> WorkflowManifestDiagnostic:
    line, column = (
        locate_workflow_manifest_path(source, path) if source is not None else (None, None)
    )
    return WorkflowManifestDiagnostic(
        severity=WorkflowManifestDiagnosticSeverity.ERROR,
        message=message,
        path=path,
        line=line,
        column=column,
    )


def _compile_reference(
    reference: WorkflowManifestReference,
    step_index_by_id: dict[str, int],
) -> dict[str, object]:
    if reference.source == "inputs":
        if reference.path is None:
            raise ValueError("Input references must include a path")
        return {"from": "input", "path": reference.path}

    slot = _resolve_slot(reference)
    payload: dict[str, object] = {
        "from": "step",
        "stepIndex": _resolve_step_index(reference, step_index_by_id),
        "slot": slot,
    }
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _compile_output_spec(
    reference: WorkflowManifestReference,
    step_index_by_id: dict[str, int],
) -> dict[str, object]:
    slot = _resolve_slot(reference)
    payload: dict[str, object] = {
        "kind": "slot",
        "stepIndex": _resolve_step_index(reference, step_index_by_id),
        "slot": slot,
    }
    if reference.output_path is not None:
        payload["path"] = reference.output_path
    return payload


def _resolve_step_index(
    reference: WorkflowManifestReference,
    step_index_by_id: dict[str, int],
) -> int:
    if reference.step_id is None:
        raise ValueError("Step output references must include a step id")
    return step_index_by_id[reference.step_id]


def _resolve_slot(reference: WorkflowManifestReference) -> str:
    if reference.slot is None:
        raise ValueError("Step output references must include a slot")
    return reference.slot


__all__ = ["WorkflowManifestCompilerError", "compile_workflow_manifest"]
