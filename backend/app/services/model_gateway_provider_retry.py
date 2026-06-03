from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

import openai

from app.agents.runtime_tools.failure_taxonomy import (
    PROVIDER_NETWORK_FAILURE,
    PROVIDER_TRANSPORT_FAILURE,
    ToolFailureClassification,
    provider_status_failure_classification,
)

_PROVIDER_RETRY_POLICY = "transientProviderRetry/v1"
_PROVIDER_RETRY_MAX_ATTEMPTS = 3
_PROVIDER_RETRY_BASE_DELAY_MS = 500
_PROVIDER_RETRY_BACKOFF_MULTIPLIER = 2
_PROVIDER_RETRY_MAX_DELAY_MS = 8000
_PROVIDER_RETRY_AFTER_MAX_DELAY_MS = 10000
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429})
_RETRY_AFTER_STATUS_CODES = frozenset({429, 503})
_ALLOWED_ATTEMPT_OUTCOMES = frozenset({"retryScheduled", "retryAfterHonored", "exhausted"})


def _metadata_without_none(payload: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class ProviderRetryPolicy:
    policy: str = _PROVIDER_RETRY_POLICY
    max_attempts: int = _PROVIDER_RETRY_MAX_ATTEMPTS
    base_delay_ms: int = _PROVIDER_RETRY_BASE_DELAY_MS
    backoff_multiplier: int = _PROVIDER_RETRY_BACKOFF_MULTIPLIER
    max_delay_ms: int = _PROVIDER_RETRY_MAX_DELAY_MS
    max_retry_after_ms: int = _PROVIDER_RETRY_AFTER_MAX_DELAY_MS

    def is_retryable(self, exc: BaseException) -> bool:
        if isinstance(exc, openai.APITimeoutError):
            return True
        if isinstance(exc, openai.APIConnectionError):
            return True
        if isinstance(exc, openai.APIStatusError):
            return self.is_retryable_status_code(_provider_status_code(exc))
        return False

    def is_retryable_status_code(self, status_code: object) -> bool:
        if not isinstance(status_code, int):
            return False
        return status_code in _RETRYABLE_STATUS_CODES or status_code >= 500

    def retry_after_delay_ms(self, exc: BaseException) -> int | None:
        if not isinstance(exc, openai.APIStatusError):
            return None
        status_code = _provider_status_code(exc)
        if status_code is None or status_code not in _RETRY_AFTER_STATUS_CODES:
            return None
        retry_after_ms = _retry_after_ms_from_response(getattr(exc, "response", None))
        if retry_after_ms is None:
            return None
        if retry_after_ms <= 0 or retry_after_ms > self.max_retry_after_ms:
            return None
        return retry_after_ms

    def build_attempt(
        self,
        exc: BaseException,
        *,
        outcome: str,
        attempt: int,
        delay_ms: int | None = None,
    ) -> ProviderRetryAttempt:
        return ProviderRetryAttempt(
            attempt=attempt,
            outcome=outcome,
            error_code=_provider_error_code(exc),
            status_code=_provider_status_code(exc),
            failure_class=_provider_failure_classification(exc).failure_class.value,
            delay_ms=delay_ms,
        )


@dataclass(frozen=True, slots=True)
class ProviderRetryAttempt:
    attempt: int
    outcome: str
    error_code: str
    failure_class: str
    status_code: int | None = None
    delay_ms: int | None = None

    def __post_init__(self) -> None:
        if self.attempt < 1:
            raise ValueError("Provider retry attempts must use 1-based numbering.")
        if self.outcome not in _ALLOWED_ATTEMPT_OUTCOMES:
            raise ValueError(f"Unsupported provider retry outcome {self.outcome!r}.")

    def to_metadata(self) -> dict[str, object]:
        return _metadata_without_none(
            {
                "attempt": self.attempt,
                "outcome": self.outcome,
                "errorCode": self.error_code,
                "statusCode": self.status_code,
                "failureClass": self.failure_class,
                "delayMs": self.delay_ms,
            }
        )


@dataclass(slots=True)
class ProviderRetryRecorder:
    policy: ProviderRetryPolicy = field(default_factory=ProviderRetryPolicy)
    attempts: list[ProviderRetryAttempt] = field(default_factory=list)

    def record_retry(
        self,
        exc: BaseException,
        *,
        delay_ms: int,
        retry_after_honored: bool = False,
    ) -> ProviderRetryAttempt:
        if not self.policy.is_retryable(exc):
            raise ValueError("Provider retry attempts require retryable provider failures.")
        attempt = self.policy.build_attempt(
            exc,
            outcome="retryAfterHonored" if retry_after_honored else "retryScheduled",
            attempt=len(self.attempts) + 1,
            delay_ms=delay_ms,
        )
        self.attempts.append(attempt)
        return attempt

    def record_exhausted(self, exc: BaseException) -> ProviderRetryAttempt:
        if not self.policy.is_retryable(exc):
            raise ValueError("Provider retry attempts require retryable provider failures.")
        attempt = self.policy.build_attempt(
            exc,
            outcome="exhausted",
            attempt=len(self.attempts) + 1,
        )
        self.attempts.append(attempt)
        return attempt

    def success_metadata(self) -> dict[str, object] | None:
        if not self.attempts:
            return None
        return self._metadata(terminal_outcome="succeededAfterRetry")

    def exhausted_metadata(self) -> dict[str, object] | None:
        if not self.attempts:
            return None
        return self._metadata(terminal_outcome="exhausted")

    def _metadata(self, *, terminal_outcome: str) -> dict[str, object]:
        return {
            "policy": self.policy.policy,
            "maxAttempts": self.policy.max_attempts,
            "attempts": [attempt.to_metadata() for attempt in self.attempts],
            "terminalOutcome": terminal_outcome,
        }


def call_with_provider_retry[
    T
](
    operation: Callable[[], T],
    *,
    policy: ProviderRetryPolicy | None = None,
    recorder: ProviderRetryRecorder | None = None,
    sleep: Callable[[float], object] | None = None,
    random_int: Callable[[int, int], int] | None = None,
) -> T:
    active_policy, active_recorder = _resolve_retry_components(
        policy=policy,
        recorder=recorder,
    )
    sleeper = sleep or time.sleep
    jitter_random_int = random_int or random.randint
    while True:
        try:
            return operation()
        except Exception as exc:
            if not active_policy.is_retryable(exc):
                raise
            attempt = len(active_recorder.attempts) + 1
            if attempt >= active_policy.max_attempts:
                _ = active_recorder.record_exhausted(exc)
                raise
            retry_after_delay_ms = active_policy.retry_after_delay_ms(exc)
            if retry_after_delay_ms is not None:
                delay_ms = retry_after_delay_ms
            else:
                capped_delay_ms = _retry_backoff_delay_ms(active_policy, attempt=attempt)
                delay_ms = _full_jitter_delay_ms(
                    capped_delay_ms,
                    random_int=jitter_random_int,
                )
            _ = active_recorder.record_retry(
                exc,
                delay_ms=delay_ms,
                retry_after_honored=retry_after_delay_ms is not None,
            )
            _ = sleeper(delay_ms / 1000)


def _resolve_retry_components(
    *,
    policy: ProviderRetryPolicy | None,
    recorder: ProviderRetryRecorder | None,
) -> tuple[ProviderRetryPolicy, ProviderRetryRecorder]:
    if recorder is None:
        active_policy = policy or ProviderRetryPolicy()
        return active_policy, ProviderRetryRecorder(policy=active_policy)
    active_policy = policy or recorder.policy
    if recorder.policy != active_policy:
        raise ValueError("Provider retry recorder policy mismatch.")
    return active_policy, recorder


def _retry_backoff_delay_ms(
    policy: ProviderRetryPolicy,
    *,
    attempt: int,
) -> int:
    exponent = max(attempt - 1, 0)
    delay_ms = int(policy.base_delay_ms) * (int(policy.backoff_multiplier) ** exponent)
    max_delay_ms = int(policy.max_delay_ms)
    return delay_ms if delay_ms <= max_delay_ms else max_delay_ms


def _full_jitter_delay_ms(
    capped_delay_ms: int,
    *,
    random_int: Callable[[int, int], int],
) -> int:
    if capped_delay_ms < 0:
        raise ValueError("Provider retry delay cannot be negative.")
    return random_int(0, capped_delay_ms)


def _provider_error_code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    if isinstance(exc, openai.APITimeoutError):
        return "agent_provider_timeout"
    if isinstance(exc, openai.APIConnectionError):
        return "agent_provider_connection_error"
    if isinstance(exc, openai.APIStatusError):
        return "agent_provider_status_error"
    if isinstance(exc, openai.APIError):
        return "agent_provider_error"
    return "agent_provider_error"


def _provider_status_code(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    return response_status_code if isinstance(response_status_code, int) else None


def _provider_failure_classification(exc: BaseException) -> ToolFailureClassification:
    classification = getattr(exc, "failure_classification", None)
    if isinstance(classification, ToolFailureClassification):
        return classification
    if isinstance(exc, openai.APITimeoutError):
        return PROVIDER_NETWORK_FAILURE
    if isinstance(exc, openai.APIConnectionError):
        return PROVIDER_NETWORK_FAILURE
    if isinstance(exc, openai.APIStatusError):
        return provider_status_failure_classification(_provider_status_code(exc))
    return PROVIDER_TRANSPORT_FAILURE


def _retry_after_ms_from_response(response: object) -> int | None:
    raw_headers = getattr(response, "headers", None)
    if not isinstance(raw_headers, Mapping):
        return None
    headers = cast(Mapping[str, object], raw_headers)
    retry_after_ms = _header_text(headers, "retry-after-ms")
    if retry_after_ms is not None:
        parsed = _parse_positive_milliseconds(retry_after_ms)
        if parsed is not None:
            return parsed
    retry_after = _header_text(headers, "retry-after")
    if retry_after is None:
        return None
    seconds_delay = _parse_positive_seconds(retry_after)
    if seconds_delay is not None:
        return seconds_delay
    return _parse_retry_after_http_date(retry_after)


def _header_text(headers: Mapping[str, object], key: str) -> str | None:
    value = headers.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_positive_milliseconds(value: str) -> int | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_positive_seconds(value: str) -> int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    delay_ms = int(parsed * 1000)
    return delay_ms if delay_ms > 0 else None


def _parse_retry_after_http_date(value: str) -> int | None:
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    delay_ms = int((retry_at - datetime.now(UTC)).total_seconds() * 1000)
    return delay_ms if delay_ms > 0 else None


__all__ = [
    "ProviderRetryAttempt",
    "ProviderRetryPolicy",
    "ProviderRetryRecorder",
    "call_with_provider_retry",
]
