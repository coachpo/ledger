from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from app.agents.runtime_tools.failure_taxonomy import (
    OUTPUT_SCHEMA_FAILURE,
    RETRY_BOUND_EXHAUSTED_FAILURE,
)
from app.services.model_gateway_dto import ModelExecutionRequest, ModelGatewayError

OutputStrategy = Literal["strictJsonSchema", "jsonObjectWithValidation", "plainText"]

_STRICT_SCHEMA_CAPABILITY = "strictJsonSchemaOutput"
_JSON_OBJECT_CAPABILITY = "jsonObjectOutput"
_SUPPORTED = "supported"
_UNSUPPORTED = "unsupported"
_REQUIRE_STRICT_SCHEMA = "require_strict_schema"
_PREFER_STRICT_SCHEMA = "prefer_strict_schema"
_ALLOW_JSON_OBJECT_VALIDATION = "allow_json_object_validation"
_ALLOW_PLAIN_TEXT = "allow_plain_text"


@dataclass(frozen=True, slots=True)
class OutputValidationResult:
    output: Any
    details: list[dict[str, str]] | None = None


@dataclass(frozen=True, slots=True)
class ModelOutputStrategySelection:
    strategy: OutputStrategy

    @property
    def max_validation_attempts(self) -> int:
        return 2 if self.strategy == "jsonObjectWithValidation" else 1

    @property
    def uses_server_validation(self) -> bool:
        return self.strategy in {"jsonObjectWithValidation", "plainText"}

    @property
    def sends_native_format(self) -> bool:
        return self.strategy in {"strictJsonSchema", "jsonObjectWithValidation"}


def select_output_strategy(request: ModelExecutionRequest) -> ModelOutputStrategySelection:
    policy = request.connection.output_strategy_policy
    strict_status = _capability_status(request, _STRICT_SCHEMA_CAPABILITY)
    json_status = _capability_status(request, _JSON_OBJECT_CAPABILITY)

    if policy == _ALLOW_PLAIN_TEXT:
        return ModelOutputStrategySelection(strategy="plainText")
    if policy == _REQUIRE_STRICT_SCHEMA:
        if strict_status == _UNSUPPORTED:
            raise ModelGatewayError(
                code="model_capability_required_missing",
                message="Model connection does not support required strict JSON-schema output.",
                details=[
                    {"field": _STRICT_SCHEMA_CAPABILITY, "issue": "Capability is unsupported"}
                ],
            )
        return ModelOutputStrategySelection(strategy="strictJsonSchema")
    if policy == _ALLOW_JSON_OBJECT_VALIDATION:
        if json_status == _UNSUPPORTED:
            raise ModelGatewayError(
                code="model_capability_required_missing",
                message="Model connection does not support JSON-object output fallback.",
                details=[{"field": _JSON_OBJECT_CAPABILITY, "issue": "Capability is unsupported"}],
            )
        return ModelOutputStrategySelection(strategy="jsonObjectWithValidation")
    if strict_status != _UNSUPPORTED:
        return ModelOutputStrategySelection(strategy="strictJsonSchema")
    if json_status != _UNSUPPORTED:
        return ModelOutputStrategySelection(strategy="jsonObjectWithValidation")
    raise ModelGatewayError(
        code="model_capability_required_missing",
        message="Model connection does not support a structured output strategy allowed by policy.",
        details=[
            {"field": _STRICT_SCHEMA_CAPABILITY, "issue": "Capability is unsupported"},
            {"field": _JSON_OBJECT_CAPABILITY, "issue": "Capability is unsupported"},
        ],
    )


def validate_model_output(
    request: ModelExecutionRequest,
    output: Any,
) -> OutputValidationResult:
    runtime_model = request.output_schema.runtime_model
    if runtime_model is None:
        return OutputValidationResult(output=output)
    try:
        validated = runtime_model.model_validate(output)
    except ValidationError as exc:
        return OutputValidationResult(
            output=None,
            details=_validation_details_from_pydantic_error(exc),
        )
    return OutputValidationResult(output=validated.model_dump(mode="json"))


def validation_retry_input(
    *,
    original_input: str,
    validation_details: list[dict[str, str]],
) -> str:
    return "\n\n".join(
        (
            original_input,
            "The previous JSON response failed server-side schema validation. "
            "Return one corrected JSON object only, with no markdown or explanatory text.",
            "Validation errors: "
            + json.dumps(validation_details, ensure_ascii=False, sort_keys=True),
        )
    )


def exhausted_validation_error(details: list[dict[str, str]]) -> ModelGatewayError:
    return ModelGatewayError(
        code="model_output_retry_exhausted",
        message="Model output failed server-side schema validation after one retry.",
        details=details,
        failure_classification=RETRY_BOUND_EXHAUSTED_FAILURE,
    )


def validation_failed_error(details: list[dict[str, str]]) -> ModelGatewayError:
    return ModelGatewayError(
        code="model_output_validation_failed",
        message="Model output failed server-side schema validation.",
        details=details,
        failure_classification=OUTPUT_SCHEMA_FAILURE,
    )


def _capability_status(request: ModelExecutionRequest, key: str) -> str | None:
    capabilities = request.connection.capabilities or {}
    raw_state = capabilities.get(key)
    if not isinstance(raw_state, dict):
        return None
    raw_status = raw_state.get("status")
    return raw_status if isinstance(raw_status, str) else None


def _validation_details_from_pydantic_error(exc: ValidationError) -> list[dict[str, str]]:
    details: list[dict[str, str]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(str(part) for part in location) if location else "output"
        details.append(
            {
                "field": field or "output",
                "issue": str(error.get("msg", "Invalid value")),
            }
        )
    return details


__all__ = [
    "ModelOutputStrategySelection",
    "OutputStrategy",
    "OutputValidationResult",
    "exhausted_validation_error",
    "select_output_strategy",
    "validate_model_output",
    "validation_failed_error",
    "validation_retry_input",
]
