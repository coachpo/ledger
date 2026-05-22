from __future__ import annotations

from typing import Final, NoReturn

from app.core.errors import business_rule_error

LEGACY_AUTHORING_RUNTIME_BLOCKED: Final = "runtime-blocked"


def raise_legacy_global_authoring_runtime_blocked(surface: str) -> NoReturn:
    raise business_rule_error(
        "legacy_global_authoring_runtime_blocked",
        "Legacy global authoring execution is retired; use Workflow Packages instead.",
        details=[
            {
                "field": "targetKind",
                "issue": f"{surface} is runtime-blocked after the Workflow Package cutover.",
            }
        ],
    )


__all__ = [
    "LEGACY_AUTHORING_RUNTIME_BLOCKED",
    "raise_legacy_global_authoring_runtime_blocked",
]
