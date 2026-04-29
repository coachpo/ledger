from __future__ import annotations

from typing import cast

from app.schemas.workflow import WorkflowCreate
from app.schemas.workflow_manifest import (
    WorkflowManifest,
    WorkflowManifestDiagnostic,
    WorkflowManifestReference,
)
from app.services.workflow_manifest_parser import parse_workflow_manifest


class WorkflowManifestCompilerError(ValueError):
    def __init__(self, diagnostics: list[WorkflowManifestDiagnostic]) -> None:
        super().__init__("Workflow manifest could not be compiled")
        self.diagnostics: list[WorkflowManifestDiagnostic] = diagnostics


def compile_workflow_manifest(source: str | WorkflowManifest) -> dict[str, object]:
    manifest = _resolve_manifest(source)
    step_index_by_id = {step.id: index for index, step in enumerate(manifest.steps, start=1)}
    payload = {
        "key": manifest.metadata.key,
        "name": manifest.metadata.name,
        "description": manifest.metadata.description,
        "inputSchema": manifest.input_schema,
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
    return cast(
        dict[str, object],
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
    )


def _resolve_manifest(source: str | WorkflowManifest) -> WorkflowManifest:
    if isinstance(source, WorkflowManifest):
        return source

    result = parse_workflow_manifest(source)
    if result.manifest is None or result.diagnostics:
        raise WorkflowManifestCompilerError(result.diagnostics)
    return result.manifest


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
