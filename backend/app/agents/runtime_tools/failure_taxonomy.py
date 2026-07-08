from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class ToolFailureDisposition(StrEnum):
    RETRYABLE = "retryable"
    FATAL = "fatal"


class ToolFailurePhase(StrEnum):
    PRE_DISPATCH = "pre_dispatch"
    DISPATCH = "dispatch"
    POST_DISPATCH = "post_dispatch"
    PROVIDER = "provider"
    TRANSPORT = "transport"
    EXECUTOR = "executor"
    POLICY = "policy"
    OUTPUT_VALIDATION = "output_validation"


class ToolFailureSource(StrEnum):
    PROVIDER = "provider"
    NATIVE_TOOL = "native_tool"
    MCP_TOOL = "mcp_tool"
    MODEL_CONNECTION = "model_connection"
    PLATFORM = "platform"


class ToolFailureClass(StrEnum):
    PROVIDER_TOOL_ARGUMENT_JSON_INVALID = "provider_tool_argument_json_invalid"
    PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID = "provider_tool_argument_object_invalid"
    NATIVE_TOOL_ARGUMENT_VALIDATION = "native_tool_argument_validation"
    MCP_TOOL_ARGUMENT_JSON_INVALID = "mcp_tool_argument_json_invalid"
    MCP_TOOL_ARGUMENT_SCHEMA_INVALID = "mcp_tool_argument_schema_invalid"
    AUTH = "auth"
    PERMISSION = "permission"
    GRANT = "grant"
    SECRET_CONTEXT = "secret_context"
    UNSUPPORTED_TOOL = "unsupported_tool"
    PROVIDER_NETWORK = "provider_network"
    PROVIDER_TRANSPORT = "provider_transport"
    MCP_TRANSPORT = "mcp_transport"
    EXECUTOR = "executor"
    BUSINESS_RULE = "business_rule"
    POLICY = "policy"
    OUTPUT_SCHEMA = "output_schema"
    RETRY_BOUND_EXHAUSTED = "retry_bound_exhausted"


RETRYABLE_FAILURE_CLASSES: Final[frozenset[ToolFailureClass]] = frozenset(
    {
        ToolFailureClass.PROVIDER_TOOL_ARGUMENT_JSON_INVALID,
        ToolFailureClass.PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID,
        ToolFailureClass.NATIVE_TOOL_ARGUMENT_VALIDATION,
        ToolFailureClass.MCP_TOOL_ARGUMENT_JSON_INVALID,
        ToolFailureClass.MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
    }
)


@dataclass(frozen=True, slots=True)
class ToolFailureClassification:
    failure_class: ToolFailureClass
    source: ToolFailureSource
    phase: ToolFailurePhase
    retryable: bool = False

    def __post_init__(self) -> None:
        expected_retryable = self.failure_class in RETRYABLE_FAILURE_CLASSES
        if self.retryable != expected_retryable:
            raise ValueError(
                f"{self.failure_class.value} retryable must be {expected_retryable!r}."
            )

    @property
    def disposition(self) -> ToolFailureDisposition:
        if self.retryable:
            return ToolFailureDisposition.RETRYABLE
        return ToolFailureDisposition.FATAL

    def to_metadata(self) -> dict[str, object]:
        return {
            "failureClass": self.failure_class.value,
            "retryable": self.retryable,
            "disposition": self.disposition.value,
            "phase": self.phase.value,
            "source": self.source.value,
        }


PROVIDER_TOOL_ARGUMENT_JSON_INVALID = ToolFailureClassification(
    failure_class=ToolFailureClass.PROVIDER_TOOL_ARGUMENT_JSON_INVALID,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.PRE_DISPATCH,
    retryable=True,
)
PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID = ToolFailureClassification(
    failure_class=ToolFailureClass.PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.PRE_DISPATCH,
    retryable=True,
)
NATIVE_TOOL_ARGUMENT_VALIDATION = ToolFailureClassification(
    failure_class=ToolFailureClass.NATIVE_TOOL_ARGUMENT_VALIDATION,
    source=ToolFailureSource.NATIVE_TOOL,
    phase=ToolFailurePhase.PRE_DISPATCH,
    retryable=True,
)
MCP_TOOL_ARGUMENT_JSON_INVALID = ToolFailureClassification(
    failure_class=ToolFailureClass.MCP_TOOL_ARGUMENT_JSON_INVALID,
    source=ToolFailureSource.MCP_TOOL,
    phase=ToolFailurePhase.PRE_DISPATCH,
    retryable=True,
)
MCP_TOOL_ARGUMENT_SCHEMA_INVALID = ToolFailureClassification(
    failure_class=ToolFailureClass.MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
    source=ToolFailureSource.MCP_TOOL,
    phase=ToolFailurePhase.PRE_DISPATCH,
    retryable=True,
)
AUTH_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.AUTH,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.PROVIDER,
)
PERMISSION_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.PERMISSION,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.DISPATCH,
)
GRANT_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.GRANT,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.DISPATCH,
)
SECRET_CONTEXT_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.SECRET_CONTEXT,
    source=ToolFailureSource.MODEL_CONNECTION,
    phase=ToolFailurePhase.DISPATCH,
)
UNSUPPORTED_TOOL_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.UNSUPPORTED_TOOL,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.DISPATCH,
)
PROVIDER_NETWORK_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.PROVIDER_NETWORK,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.TRANSPORT,
)
PROVIDER_TRANSPORT_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.PROVIDER_TRANSPORT,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.TRANSPORT,
)
MCP_TRANSPORT_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.MCP_TRANSPORT,
    source=ToolFailureSource.MCP_TOOL,
    phase=ToolFailurePhase.TRANSPORT,
)
EXECUTOR_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.EXECUTOR,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.EXECUTOR,
)
BUSINESS_RULE_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.BUSINESS_RULE,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.EXECUTOR,
)
POLICY_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.POLICY,
    source=ToolFailureSource.PLATFORM,
    phase=ToolFailurePhase.POLICY,
)
OUTPUT_SCHEMA_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.OUTPUT_SCHEMA,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.OUTPUT_VALIDATION,
)
RETRY_BOUND_EXHAUSTED_FAILURE = ToolFailureClassification(
    failure_class=ToolFailureClass.RETRY_BOUND_EXHAUSTED,
    source=ToolFailureSource.PROVIDER,
    phase=ToolFailurePhase.OUTPUT_VALIDATION,
)

_ERROR_CODE_CLASSIFICATIONS: Final[dict[str, ToolFailureClassification]] = {
    "agent_model_connection_api_key_missing": SECRET_CONTEXT_FAILURE,
    "agent_model_connection_api_style_unsupported": SECRET_CONTEXT_FAILURE,
    "agent_tool_call_invalid": NATIVE_TOOL_ARGUMENT_VALIDATION,
    "agent_tool_call_unsupported": UNSUPPORTED_TOOL_FAILURE,
    "agent_tool_dependency_missing": SECRET_CONTEXT_FAILURE,
    "agent_tool_definition_invalid": EXECUTOR_FAILURE,
    "agent_tool_round_limit_exceeded": RETRY_BOUND_EXHAUSTED_FAILURE,
    "agent_provider_connection_error": PROVIDER_NETWORK_FAILURE,
    "agent_provider_error": PROVIDER_TRANSPORT_FAILURE,
    "agent_provider_response_empty": PROVIDER_TRANSPORT_FAILURE,
    "agent_provider_status_error": PROVIDER_TRANSPORT_FAILURE,
    "agent_provider_timeout": PROVIDER_NETWORK_FAILURE,
    "agent_result_invalid": EXECUTOR_FAILURE,
    "capability_tool_keys_invalid": GRANT_FAILURE,
    "mcp_runtime_transport_error": MCP_TRANSPORT_FAILURE,
    "mcp_runtime_transport_unavailable": MCP_TRANSPORT_FAILURE,
    "mcp_server_disabled": MCP_TRANSPORT_FAILURE,
    "mcp_server_missing": MCP_TRANSPORT_FAILURE,
    "mcp_server_pin_invalid": MCP_TRANSPORT_FAILURE,
    "mcp_server_status_invalid": MCP_TRANSPORT_FAILURE,
    "mcp_tool_arguments_invalid": MCP_TOOL_ARGUMENT_SCHEMA_INVALID,
    "mcp_tool_call_unsupported": UNSUPPORTED_TOOL_FAILURE,
    "mcp_tool_descriptor_invalid": MCP_TRANSPORT_FAILURE,
    "mcp_tool_descriptor_missing": MCP_TRANSPORT_FAILURE,
    "mcp_tool_name_collision": MCP_TRANSPORT_FAILURE,
    "mcp_tool_owner_missing": MCP_TRANSPORT_FAILURE,
    "mcp_tool_schema_missing": MCP_TRANSPORT_FAILURE,
    "mcp_tool_snapshot_drift": MCP_TRANSPORT_FAILURE,
    "mcp_tool_snapshots_invalid": MCP_TRANSPORT_FAILURE,
    "mcp_tool_snapshots_missing": MCP_TRANSPORT_FAILURE,
    "model_capability_required_missing": POLICY_FAILURE,
    "model_output_retry_exhausted": RETRY_BOUND_EXHAUSTED_FAILURE,
    "model_output_validation_failed": OUTPUT_SCHEMA_FAILURE,
    "model_tool_call_retry_exhausted": RETRY_BOUND_EXHAUSTED_FAILURE,
    "model_reasoning_unsupported": POLICY_FAILURE,
    "model_tool_call_payload_invalid": PROVIDER_TRANSPORT_FAILURE,
    "run_agent_model_connection_missing": SECRET_CONTEXT_FAILURE,
    "run_agent_model_connection_unavailable": SECRET_CONTEXT_FAILURE,
}


def classification_for_error_code(code: str) -> ToolFailureClassification:
    normalized = code.strip()
    exact = _ERROR_CODE_CLASSIFICATIONS.get(normalized)
    if exact is not None:
        return exact
    if "access_denied" in normalized or "permission" in normalized:
        return PERMISSION_FAILURE
    if "grant" in normalized:
        return GRANT_FAILURE
    if normalized.startswith("agent_provider_"):
        return PROVIDER_TRANSPORT_FAILURE
    if normalized.startswith("mcp_"):
        return MCP_TRANSPORT_FAILURE
    if normalized.startswith("model_"):
        return POLICY_FAILURE
    if normalized.startswith("run_") or normalized.startswith("agent_input_"):
        return BUSINESS_RULE_FAILURE
    if normalized.startswith("operation_") or normalized.startswith("workflow_"):
        return BUSINESS_RULE_FAILURE
    return EXECUTOR_FAILURE


def provider_status_failure_classification(status_code: int | None) -> ToolFailureClassification:
    if status_code == 401:
        return AUTH_FAILURE
    if status_code == 403:
        return PERMISSION_FAILURE
    return PROVIDER_TRANSPORT_FAILURE


def runtime_failure_metadata(
    classification: ToolFailureClassification | None,
) -> dict[str, object]:
    if classification is None:
        return {}
    return {"failureTaxonomy": classification.to_metadata()}


__all__ = [
    "AUTH_FAILURE",
    "BUSINESS_RULE_FAILURE",
    "EXECUTOR_FAILURE",
    "GRANT_FAILURE",
    "MCP_TOOL_ARGUMENT_JSON_INVALID",
    "MCP_TOOL_ARGUMENT_SCHEMA_INVALID",
    "MCP_TRANSPORT_FAILURE",
    "NATIVE_TOOL_ARGUMENT_VALIDATION",
    "OUTPUT_SCHEMA_FAILURE",
    "PERMISSION_FAILURE",
    "POLICY_FAILURE",
    "PROVIDER_NETWORK_FAILURE",
    "PROVIDER_TOOL_ARGUMENT_JSON_INVALID",
    "PROVIDER_TOOL_ARGUMENT_OBJECT_INVALID",
    "PROVIDER_TRANSPORT_FAILURE",
    "RETRYABLE_FAILURE_CLASSES",
    "RETRY_BOUND_EXHAUSTED_FAILURE",
    "SECRET_CONTEXT_FAILURE",
    "UNSUPPORTED_TOOL_FAILURE",
    "ToolFailureClass",
    "ToolFailureClassification",
    "ToolFailureDisposition",
    "ToolFailurePhase",
    "ToolFailureSource",
    "classification_for_error_code",
    "provider_status_failure_classification",
    "runtime_failure_metadata",
]
