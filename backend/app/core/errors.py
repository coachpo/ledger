from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import status
from fastapi.exceptions import RequestValidationError


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Sequence[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = list(details or [])


def not_found_error(resource_name: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_404_NOT_FOUND,
        code="not_found",
        message=f"{resource_name} not found",
    )


def business_rule_error(
    code: str, message: str, details: Sequence[dict[str, Any]] | None = None
) -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code=code,
        message=message,
        details=details,
    )


def extension_disabled_error(extension_key: str, surface: str) -> ApiError:
    return ApiError(
        status_code=status.HTTP_403_FORBIDDEN,
        code="extension_disabled",
        message="Extension is disabled",
        details=[{"extensionKey": extension_key, "surface": surface}],
    )


def validation_error(message: str, details: Sequence[dict[str, Any]] | None = None) -> ApiError:
    return ApiError(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        code="validation_error",
        message=message,
        details=details,
    )


def malformed_file_error(message: str, details: Sequence[dict[str, Any]] | None = None) -> ApiError:
    return ApiError(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="malformed_file",
        message=message,
        details=details,
    )


def request_validation_to_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    for error in exc.errors():
        location = error.get("loc", ())
        field_parts = [str(part) for part in location if part not in {"body", "query", "path"}]
        details.append(
            {
                "field": (
                    ".".join(field_parts)
                    if field_parts
                    else str(location[-1])
                    if location
                    else "request"
                ),
                "issue": str(error.get("msg", "Invalid value")),
            }
        )
    return details
