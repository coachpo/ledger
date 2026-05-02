from __future__ import annotations

from typing import Any, cast

from app.schemas.workflow import WorkflowCreate
from app.schemas.workflow_manifest import (
    WorkflowManifest,
    WorkflowManifestDiagnostic,
    WorkflowManifestDiagnosticSeverity,
    WorkflowManifestReference,
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
    def resolve_registry_ref(self, key: str, version: int | None) -> None:
        return None


def compile_workflow_manifest(
    source: str | WorkflowManifest,
    *,
    schema_compiler: OutputSchemaCompiler | None = None,
) -> dict[str, object]:
    manifest, source_text = _resolve_manifest(source)
    input_schema = _normalize_input_schema(
        manifest.input_schema,
        source=source_text,
        schema_compiler=schema_compiler,
    )
    step_index_by_id = {step.id: index for index, step in enumerate(manifest.steps, start=1)}
    payload = {
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
    return cast(
        dict[str, object],
        WorkflowCreate.model_validate(payload).model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
    )


def _resolve_manifest(source: str | WorkflowManifest) -> tuple[WorkflowManifest, str | None]:
    if isinstance(source, WorkflowManifest):
        return source, None

    result = parse_workflow_manifest(source)
    if result.manifest is None or result.diagnostics:
        raise WorkflowManifestCompilerError(result.diagnostics)
    return result.manifest, source


def _normalize_input_schema(
    input_schema: dict[str, Any],
    *,
    source: str | None,
    schema_compiler: OutputSchemaCompiler | None,
) -> dict[str, object]:
    compiler = schema_compiler or OutputSchemaCompiler(
        cast(Any, _UnavailableOutputSchemaRepository())
    )
    try:
        prepared_schema = compiler.normalize_payload(
            builder=None,
            json_schema=input_schema,
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
