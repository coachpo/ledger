from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://ledger:ledger@localhost:25432/ledger",
        alias="DATABASE_URL",
    )
    quote_provider_timeout_seconds: float = Field(default=5.0, alias="QUOTE_PROVIDER_TIMEOUT")
    quote_provider_backend: str = Field(default="yahoo", alias="QUOTE_PROVIDER_BACKEND")
    quote_stale_after_minutes: int = Field(default=15, alias="QUOTE_STALE_AFTER_MINUTES")
    agent_platform_encryption_key: str = Field(
        default="ledger-agent-platform-dev-key",
        alias="AGENT_PLATFORM_ENCRYPTION_KEY",
    )
    market_data_cache_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".cache" / "market_data"),
        alias="MARKET_DATA_CACHE_DIR",
    )
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    mcp_runtime_enabled: bool = Field(default=False, alias="MCP_RUNTIME_ENABLED")
    mcp_runtime_timeout_seconds: float = Field(default=5.0, alias="MCP_RUNTIME_TIMEOUT")
    mcp_stdio_allowed_commands: Annotated[list[str], NoDecode] = Field(
        default=["node", "npx", "python", "python3"],
        alias="MCP_STDIO_ALLOWED_COMMANDS",
    )
    cors_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default=[
            "http://127.0.0.1:25173",
            "http://localhost:25173",
            "http://127.0.0.1:25174",
            "http://localhost:25174",
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        alias="CORS_ALLOWED_ORIGINS",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("cors_allowed_origins", "mcp_stdio_allowed_commands", mode="before")
    @classmethod
    def split_string_lists(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("public_base_url", mode="before")
    @classmethod
    def normalize_public_base_url(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized.rstrip("/")

    @field_validator("quote_provider_backend", mode="before")
    @classmethod
    def normalize_quote_provider_backend(cls, value: object) -> str:
        normalized = str(value).strip().lower() if value is not None else "yahoo"
        if normalized not in {"yahoo", "deterministic"}:
            raise ValueError("QUOTE_PROVIDER_BACKEND must be one of: yahoo, deterministic")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
