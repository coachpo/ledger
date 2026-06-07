from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from pydantic import BaseModel, RootModel, ValidationError

from app.core.errors import business_rule_error
from app.models.output_schema import OutputSchema
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    SchemaArray,
    SchemaNode,
    SchemaObject,
)


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


def canonical_run_input_payload(
    schema_node: SchemaNode,
    validated: BaseModel,
) -> dict[str, Any]:
    validated_value: Any = validated
    if not isinstance(schema_node, SchemaObject) and isinstance(validated, RootModel):
        validated_value = validated.root
    canonical = _canonical_schema_value(schema_node, validated_value)
    if not isinstance(canonical, dict):
        return validated.model_dump(mode="json")
    return canonical


def _canonical_schema_value(schema_node: SchemaNode, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(schema_node, SchemaObject):
        return _canonical_object_value(schema_node, value)
    if isinstance(schema_node, SchemaArray):
        return [_canonical_schema_value(schema_node.items, item) for item in value]
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return deepcopy(value)


def _canonical_object_value(schema_node: SchemaObject, value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        fields_set = set(value.model_fields_set)
        values_by_name = {field.name: getattr(value, field.name) for field in schema_node.fields}
    else:
        raw_values = cast(dict[str, Any], value)
        fields_set = set(raw_values)
        values_by_name = raw_values

    canonical: dict[str, Any] = {}
    for field in schema_node.fields:
        include_field = field.required or field.name in fields_set or field.schema.has_default
        if not include_field or field.name not in values_by_name:
            continue
        field_value = values_by_name[field.name]
        if field_value is None:
            if field.schema.nullable:
                canonical[field.name] = None
            continue
        canonical[field.name] = _canonical_schema_value(field.schema, field_value)
    return canonical


def validate_run_input_payload(
    *,
    schema_compiler: OutputSchemaCompiler,
    input_schema: dict[str, Any],
    input_payload: dict[str, Any],
    candidate_key: str,
    resource_name: str,
    error_code: str = "run_invalid_input",
    failure_message: str | None = None,
) -> dict[str, Any]:
    input_model = build_run_input_model(
        schema_compiler,
        input_schema,
        candidate_key=candidate_key,
    )
    schema_node = schema_compiler.parse_json_schema_node(
        input_schema,
        path=f"outputSchema[{candidate_key}@1]",
    )
    try:
        validated = input_model.model_validate(input_payload)
    except ValidationError as exc:
        raise business_rule_error(
            error_code,
            failure_message or f"Run input failed {resource_name} input schema validation",
            details=validation_details_from_pydantic_error(exc),
        ) from exc
    return canonical_run_input_payload(schema_node, validated)


__all__ = [
    "build_run_input_model",
    "canonical_run_input_payload",
    "validate_run_input_payload",
    "validation_details_from_pydantic_error",
]
