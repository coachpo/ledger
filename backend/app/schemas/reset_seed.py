from __future__ import annotations

from pydantic import field_validator

from app.schemas.common import CamelModel


class ResetSeedRequest(CamelModel):
    confirm: bool

    @field_validator("confirm")
    @classmethod
    def validate_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("confirm must be true to reset and seed the database")
        return value


class ResetSeedRead(CamelModel):
    portfolio_slugs: list[str]
    template_names: list[str]
    output_schema_keys: list[str]
    skill_keys: list[str]
    mcp_server_keys: list[str]
    agent_keys: list[str]
    report_slugs: list[str]
    workflow_keys: list[str]
