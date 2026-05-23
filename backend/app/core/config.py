from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://signaldeck:signaldeck@localhost:25432/signaldeck",
        alias="DATABASE_URL",
    )
    quote_provider_timeout_seconds: float = Field(default=5.0, alias="QUOTE_PROVIDER_TIMEOUT")
    quote_provider_backend: str = Field(default="yahoo", alias="QUOTE_PROVIDER_BACKEND")
    quote_stale_after_minutes: int = Field(default=15, alias="QUOTE_STALE_AFTER_MINUTES")
    agent_platform_encryption_key: str = Field(
        default="signaldeck-agent-platform-dev-key",
        alias="AGENT_PLATFORM_ENCRYPTION_KEY",
    )
    market_data_cache_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".cache" / "market_data"),
        alias="MARKET_DATA_CACHE_DIR",
    )
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    mcp_runtime_enabled: bool = Field(default=False, alias="MCP_RUNTIME_ENABLED")
    mcp_runtime_timeout_seconds: float = Field(default=5.0, alias="MCP_RUNTIME_TIMEOUT")
    http_operation_allowed_methods: Annotated[list[str], NoDecode] = Field(
        default=["GET", "POST"],
        alias="HTTP_OPERATION_ALLOWED_METHODS",
    )
    http_operation_allow_insecure_http: bool = Field(
        default=False,
        alias="HTTP_OPERATION_ALLOW_INSECURE_HTTP",
    )
    http_operation_block_private_networks: bool = Field(
        default=True,
        alias="HTTP_OPERATION_BLOCK_PRIVATE_NETWORKS",
    )
    http_operation_timeout_max_seconds: int = Field(
        default=30,
        alias="HTTP_OPERATION_TIMEOUT_MAX_SECONDS",
        gt=0,
    )
    http_operation_request_max_bytes: int = Field(
        default=131072,
        alias="HTTP_OPERATION_REQUEST_MAX_BYTES",
        gt=0,
    )
    http_operation_response_max_bytes: int = Field(
        default=262144,
        alias="HTTP_OPERATION_RESPONSE_MAX_BYTES",
        gt=0,
    )
    http_operation_max_redirects: int = Field(
        default=0,
        alias="HTTP_OPERATION_MAX_REDIRECTS",
        ge=0,
    )
    run_scheduler_max_active_runs: int = Field(
        default=4,
        alias="RUN_SCHEDULER_MAX_ACTIVE_RUNS",
        ge=1,
    )
    run_scheduler_max_active_per_package: int = Field(
        default=1,
        alias="RUN_SCHEDULER_MAX_ACTIVE_PER_PACKAGE",
        ge=1,
    )
    run_scheduler_poll_interval_seconds: float = Field(
        default=1.0,
        alias="RUN_SCHEDULER_POLL_INTERVAL_SECONDS",
        gt=0,
    )
    run_scheduler_heartbeat_seconds: float = Field(
        default=10.0,
        alias="RUN_SCHEDULER_HEARTBEAT_SECONDS",
        gt=0,
    )
    run_scheduler_lease_ttl_seconds: float = Field(
        default=60.0,
        alias="RUN_SCHEDULER_LEASE_TTL_SECONDS",
        gt=0,
    )
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

    @field_validator(
        "cors_allowed_origins",
        "mcp_stdio_allowed_commands",
        "http_operation_allowed_methods",
        mode="before",
    )
    @classmethod
    def split_string_lists(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("http_operation_allowed_methods")
    @classmethod
    def normalize_http_operation_allowed_methods(cls, value: list[str]) -> list[str]:
        normalized = [item.strip().upper() for item in value if item.strip()]
        if not normalized:
            raise ValueError("HTTP_OPERATION_ALLOWED_METHODS must include at least one method")
        if len(set(normalized)) != len(normalized):
            raise ValueError("HTTP_OPERATION_ALLOWED_METHODS must not contain duplicates")
        return normalized

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
