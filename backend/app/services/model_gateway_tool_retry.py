from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import cast

from app.agents.runtime_tools.failure_taxonomy import (
    RETRY_BOUND_EXHAUSTED_FAILURE,
    ToolFailureClassification,
)
from app.services.model_gateway_dto import ModelGatewayError, ModelToolCall

_TOOL_CALL_RETRY_MAX_ATTEMPTS = 1
_MAX_FAILURE_RECORDS = 3
_MAX_DETAIL_RECORDS = 5
_MAX_DETAIL_TEXT_LENGTH = 300
_EXHAUSTED_METADATA_KEY = "exhausted"


@dataclass(slots=True)
class ModelToolCallRetryState:
    max_attempts: int = _TOOL_CALL_RETRY_MAX_ATTEMPTS
    attempts_used: int = 0
    failures: list[dict[str, object]] = field(default_factory=list)

    def can_retry(
        self,
        exc: BaseException,
        *,
        prior_successful_tool_results: int = 0,
    ) -> bool:
        if prior_successful_tool_results:
            return False
        return is_retryable_tool_call_failure(exc) and self.attempts_used < self.max_attempts

    def record_retry(
        self,
        exc: BaseException,
        *,
        tool_call: ModelToolCall | None = None,
    ) -> str:
        self.attempts_used += 1
        record = self._append_failure(exc, tool_call=tool_call)
        return model_tool_call_retry_feedback(
            record,
            attempt=self.attempts_used,
            max_attempts=self.max_attempts,
        )

    def exhausted_error(
        self,
        exc: BaseException,
        *,
        tool_call: ModelToolCall | None = None,
    ) -> ModelGatewayError:
        record = self._append_failure(exc, tool_call=tool_call)
        taxonomy = record.get("failureTaxonomy")
        failure_class = "unknown"
        if isinstance(taxonomy, Mapping):
            taxonomy_record = cast(Mapping[str, object], taxonomy)
            failure_class = _bounded_text(
                taxonomy_record.get("failureClass"),
                default="unknown",
            )
        retry_word = "retry" if self.max_attempts == 1 else "retries"
        return ModelGatewayError(
            code="model_tool_call_retry_exhausted",
            message=f"Model tool call correction failed after {self.max_attempts} {retry_word}.",
            details=[
                {
                    "field": "toolCall",
                    "issue": "Retryable tool-call correction attempts were exhausted",
                    "lastFailureClass": failure_class,
                }
            ],
            failure_classification=RETRY_BOUND_EXHAUSTED_FAILURE,
            tool_retry_metadata=self.metadata(exhausted=True),
        )

    def metadata(self, *, exhausted: bool = False) -> dict[str, object] | None:
        if self.attempts_used == 0 and not self.failures:
            return None
        return {
            "attemptsUsed": self.attempts_used,
            "maxAttempts": self.max_attempts,
            _EXHAUSTED_METADATA_KEY: exhausted,
            "failures": list(self.failures[:_MAX_FAILURE_RECORDS]),
        }

    def _append_failure(
        self,
        exc: BaseException,
        *,
        tool_call: ModelToolCall | None,
    ) -> dict[str, object]:
        record = tool_call_retry_failure_record(exc, tool_call=tool_call)
        if len(self.failures) < _MAX_FAILURE_RECORDS:
            self.failures.append(record)
        return record


def is_retryable_tool_call_failure(exc: BaseException) -> bool:
    classification = _failure_classification(exc)
    return bool(classification and classification.retryable)


def tool_call_retry_failure_record(
    exc: BaseException,
    *,
    tool_call: ModelToolCall | None,
) -> dict[str, object]:
    classification = _failure_classification(exc)
    if classification is None:
        raise TypeError("Tool-call retry failures require typed failure classification.")
    record: dict[str, object] = {
        "code": str(getattr(exc, "code", "model_tool_call_failed")),
        "failureTaxonomy": classification.to_metadata(),
    }
    if tool_call is not None:
        record["toolName"] = tool_call.tool_name
        record["callId"] = tool_call.call_id
    details = _bounded_details(getattr(exc, "details", ()))
    if details:
        record["details"] = details
    return record


def model_tool_call_retry_feedback(
    record: Mapping[str, object],
    *,
    attempt: int,
    max_attempts: int,
) -> str:
    payload = {
        "toolCallRetry": {
            "attempt": attempt,
            "maxAttempts": max_attempts,
            "failure": dict(record),
        }
    }
    correction_instruction = " ".join(
        (
            "The previous tool call was rejected before execution. Emit one corrected",
            "tool call with valid JSON-object arguments, or return final JSON output if",
            "no tool is needed.",
        )
    )
    metadata_instruction = " ".join(
        (
            "Do not repeat the same invalid arguments. Use only the bounded failure",
            "metadata below; no raw argument payloads are included.",
        )
    )
    return "\n\n".join(
        (
            correction_instruction,
            metadata_instruction,
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
        )
    )


def _failure_classification(exc: BaseException) -> ToolFailureClassification | None:
    classification = getattr(exc, "failure_classification", None)
    return classification if isinstance(classification, ToolFailureClassification) else None


def _bounded_details(details: object) -> list[dict[str, str]]:
    if not isinstance(details, Sequence) or isinstance(details, (str, bytes, bytearray)):
        return []
    bounded: list[dict[str, str]] = []
    for detail in details[:_MAX_DETAIL_RECORDS]:
        if not isinstance(detail, Mapping):
            continue
        detail_record = cast(Mapping[str, object], detail)
        field = _bounded_text(detail_record.get("field"), default="detail")
        issue = _bounded_text(detail_record.get("issue"), default="Invalid value")
        bounded.append({"field": field, "issue": issue})
    return bounded


def _bounded_text(value: object, *, default: str) -> str:
    text = " ".join(str(value if value is not None else default).split()).strip()
    if not text:
        text = default
    if len(text) > _MAX_DETAIL_TEXT_LENGTH:
        return f"{text[: _MAX_DETAIL_TEXT_LENGTH - 3]}..."
    return text


__all__ = [
    "ModelToolCallRetryState",
    "is_retryable_tool_call_failure",
    "model_tool_call_retry_feedback",
    "tool_call_retry_failure_record",
]
