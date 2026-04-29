# pyright: reportMissingImports=false

from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from typing import Any, Protocol, cast

from pydantic import ValidationError
from ruamel.yaml import YAML

from app.models.workflow import WORKFLOW_MANIFEST_API_VERSION, Workflow
from app.schemas.workflow import WorkflowCreate
from app.services.workflow_manifest_compiler import compile_workflow_manifest


class WorkflowManifestDecompilerError(ValueError):
    pass


class WorkflowManifestSource(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def input_schema(self) -> dict[str, Any]: ...

    @property
    def steps(self) -> list[dict[str, Any]]: ...

    @property
    def output_spec(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class WorkflowManifestDecompileResult:
    source: str
    payload: dict[str, object]


def decompile_workflow_manifest(
    workflow: WorkflowManifestSource,
    *,
    verify_lossless: bool = True,
) -> WorkflowManifestDecompileResult:
    payload = _project_workflow_payload(workflow)
    manifest = {
        "apiVersion": WORKFLOW_MANIFEST_API_VERSION,
        "kind": "Workflow",
        "metadata": {
            "key": payload["key"],
            "name": payload["name"],
            "description": payload["description"],
        },
        "inputSchema": payload["inputSchema"],
        "steps": _decompile_steps(cast(list[dict[str, Any]], payload["steps"])),
        "output": {
            "from": _decompile_output_reference(
                cast(dict[str, Any], payload["outputSpec"]),
                cast(list[dict[str, Any]], payload["steps"]),
            )
        },
    }
    source = _dump_manifest_yaml(manifest)
    if verify_lossless:
        compiled_payload = compile_workflow_manifest(source)
        if compiled_payload != payload:
            raise WorkflowManifestDecompilerError(
                "Decompiled manifest did not round-trip losslessly"
            )
    return WorkflowManifestDecompileResult(source=source, payload=payload)


def decompile_workflow_model(
    workflow: Workflow,
    *,
    verify_lossless: bool = True,
) -> WorkflowManifestDecompileResult:
    return decompile_workflow_manifest(
        cast(WorkflowManifestSource, cast(object, workflow)),
        verify_lossless=verify_lossless,
    )


def _project_workflow_payload(workflow: WorkflowManifestSource) -> dict[str, object]:
    payload = {
        "key": workflow.key,
        "name": workflow.name,
        "description": workflow.description,
        "inputSchema": workflow.input_schema,
        "steps": [
            _project_step(step, step_offset) for step_offset, step in enumerate(workflow.steps, 1)
        ],
        "outputSpec": _project_output_spec(workflow.output_spec),
    }
    try:
        return cast(
            dict[str, object],
            WorkflowCreate.model_validate(payload).model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        )
    except ValidationError as exc:
        raise WorkflowManifestDecompilerError(str(exc)) from exc


def _project_step(step: dict[str, Any], expected_index: int) -> dict[str, object]:
    index = step.get("index")
    if index != expected_index:
        raise WorkflowManifestDecompilerError(
            f"Workflow steps must be sequential starting at 1; expected {expected_index}"
        )
    agents = step.get("agents")
    if not isinstance(agents, list):
        raise WorkflowManifestDecompilerError("Workflow step agents must be a list")
    return {
        "index": index,
        "agents": [_project_agent(agent) for agent in agents],
    }


def _project_agent(agent: object) -> dict[str, object]:
    if not isinstance(agent, dict):
        raise WorkflowManifestDecompilerError("Workflow step agent must be an object")
    payload: dict[str, object] = {
        "agentKey": agent.get("agentKey"),
        "agentVersion": agent.get("agentVersion"),
        "slot": agent.get("slot"),
        "wiring": agent.get("wiring") or {},
        "optional": bool(agent.get("optional", False)),
    }
    if payload["agentVersion"] is None:
        raise WorkflowManifestDecompilerError("Workflow step agent must include agentVersion")
    return payload


def _project_output_spec(output_spec: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": output_spec.get("kind"),
        "stepIndex": output_spec.get("stepIndex"),
        "slot": output_spec.get("slot"),
    }
    if output_spec.get("path") is not None:
        payload["path"] = output_spec["path"]
    return payload


def _decompile_steps(steps: list[dict[str, Any]]) -> list[dict[str, object]]:
    return [
        {
            "id": _step_id(step["index"]),
            "agents": [
                _decompile_agent(agent, steps)
                for agent in cast(list[dict[str, Any]], step["agents"])
            ],
        }
        for step in steps
    ]


def _decompile_agent(agent: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, object]:
    manifest_agent: dict[str, object] = {
        "slot": agent["slot"],
        "uses": f"{agent['agentKey']}@{agent['agentVersion']}",
    }
    wiring = cast(dict[str, Any], agent.get("wiring") or {})
    if wiring:
        manifest_agent["with"] = {
            field_name: _decompile_wire_reference(cast(dict[str, Any], reference), steps)
            for field_name, reference in wiring.items()
        }
    if agent.get("optional"):
        manifest_agent["optional"] = True
    return manifest_agent


def _decompile_output_reference(
    output_spec: dict[str, Any],
    steps: list[dict[str, Any]],
) -> str:
    if output_spec.get("kind") != "slot":
        raise WorkflowManifestDecompilerError("Workflow outputSpec kind must be 'slot'")
    return _step_output_expression(output_spec, steps)


def _decompile_wire_reference(reference: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    source = reference.get("from")
    if source == "input":
        path = reference.get("path")
        if not isinstance(path, str):
            raise WorkflowManifestDecompilerError("Input wiring references must include a path")
        return f"${{{{ inputs.{path} }}}}"
    if source == "step":
        return _step_output_expression(reference, steps)
    raise WorkflowManifestDecompilerError(
        "Workflow wiring references must use input or step sources"
    )


def _step_output_expression(reference: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    step_index = reference.get("stepIndex")
    slot = reference.get("slot")
    if not isinstance(step_index, int) or not isinstance(slot, str):
        raise WorkflowManifestDecompilerError(
            "Step output references must include stepIndex and slot"
        )
    _ensure_step_slot_exists(step_index, slot, steps)
    path = reference.get("path")
    suffix = f".{path}" if isinstance(path, str) and path else ""
    return f"${{{{ steps.{_step_id(step_index)}.outputs.{slot}{suffix} }}}}"


def _ensure_step_slot_exists(step_index: int, slot: str, steps: list[dict[str, Any]]) -> None:
    for step in steps:
        if step.get("index") != step_index:
            continue
        agents = cast(list[dict[str, Any]], step.get("agents") or [])
        if any(agent.get("slot") == slot for agent in agents):
            return
    raise WorkflowManifestDecompilerError(
        f"Step output reference points to missing slot {slot!r} on step {step_index}"
    )


def _step_id(step_index: int) -> str:
    return f"step_{step_index}"


def _dump_manifest_yaml(manifest: dict[str, object]) -> str:
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    stream = StringIO()
    yaml.dump(manifest, stream)
    return stream.getvalue()


__all__ = [
    "WorkflowManifestDecompileResult",
    "WorkflowManifestDecompilerError",
    "decompile_workflow_manifest",
    "decompile_workflow_model",
]
