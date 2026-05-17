from __future__ import annotations

from typing import Final, Literal, NoReturn

from app.core.errors import business_rule_error

LegacyAuthoringClassification = Literal[
    "runtime-blocked",
    "upgrade-only",
    "schema-candidate-only",
]

LEGACY_AUTHORING_RUNTIME_BLOCKED: Final[LegacyAuthoringClassification] = "runtime-blocked"
LEGACY_AUTHORING_UPGRADE_ONLY: Final[LegacyAuthoringClassification] = "upgrade-only"
LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY: Final[LegacyAuthoringClassification] = (
    "schema-candidate-only"
)

LEGACY_AUTHORING_MODULE_CLASSIFICATIONS: Final[dict[str, LegacyAuthoringClassification]] = {
    "app.services.agent_service": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.workflow_service": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.execution_plan_builder": LEGACY_AUTHORING_RUNTIME_BLOCKED,
    "app.services.capability_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.services.mcp_server_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.services.output_schema_service": LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY,
    "app.db.upgrades": LEGACY_AUTHORING_UPGRADE_ONLY,
}


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
    "LEGACY_AUTHORING_MODULE_CLASSIFICATIONS",
    "LEGACY_AUTHORING_RUNTIME_BLOCKED",
    "LEGACY_AUTHORING_SCHEMA_CANDIDATE_ONLY",
    "LEGACY_AUTHORING_UPGRADE_ONLY",
    "LegacyAuthoringClassification",
    "raise_legacy_global_authoring_runtime_blocked",
]
