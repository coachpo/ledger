from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.errors import business_rule_error
from app.models.output_schema import OutputSchema
from app.services.output_schema_compiler import OutputSchemaCompiler


def build_run_input_model(
    schema_compiler: OutputSchemaCompiler,
    input_schema: dict[str, Any],
    *,
    candidate_key: str,
) -> type[BaseModel]:
    candidate = OutputSchema(
        key=candidate_key,
        version=1,
        status="published",
        kind="standalone",
        name="Run Input Schema",
        description="Run input schema validation candidate",
        json_schema=input_schema,
        registry_refs=[],
    )
    return schema_compiler.build_runtime_model(candidate)


def validation_details_from_pydantic_error(
    exc: ValidationError,
) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(str(part) for part in location) if location else "input"
        details.append(
            {
                "field": field or "input",
                "issue": str(error.get("msg", "Invalid value")),
            }
        )
    return details


def validate_run_input_payload(
    *,
    schema_compiler: OutputSchemaCompiler,
    input_schema: dict[str, Any],
    input_payload: dict[str, Any],
    candidate_key: str,
    resource_name: str,
) -> dict[str, Any]:
    input_model = build_run_input_model(
        schema_compiler,
        input_schema,
        candidate_key=candidate_key,
    )
    try:
        validated = input_model.model_validate(input_payload)
    except ValidationError as exc:
        raise business_rule_error(
            "run_invalid_input",
            f"Run input failed {resource_name} input schema validation",
            details=validation_details_from_pydantic_error(exc),
        ) from exc
    return validated.model_dump(mode="json")


__all__ = [
    "build_run_input_model",
    "validate_run_input_payload",
    "validation_details_from_pydantic_error",
]
