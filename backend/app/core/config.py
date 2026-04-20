from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+psycopg://ledger:ledger@localhost:25432/ledger",
        alias="DATABASE_URL",
    )
    quote_provider_timeout_seconds: float = Field(default=5.0, alias="QUOTE_PROVIDER_TIMEOUT")
    quote_provider_backend: str = Field(default="yahoo", alias="QUOTE_PROVIDER_BACKEND")
    quote_stale_after_minutes: int = Field(default=15, alias="QUOTE_STALE_AFTER_MINUTES")
    runtime_agent_model: str = Field(default="gpt-4.1-mini", alias="RUNTIME_AGENT_MODEL")
    runtime_agent_base_url: str | None = Field(default=None, alias="RUNTIME_AGENT_BASE_URL")
    runtime_agent_api_key: str | None = Field(default=None, alias="RUNTIME_AGENT_API_KEY")
    agent_platform_encryption_key: str = Field(
        default="ledger-agent-platform-dev-key",
        alias="AGENT_PLATFORM_ENCRYPTION_KEY",
    )
    runtime_agent_temperature: float = Field(default=0.0, alias="RUNTIME_AGENT_TEMPERATURE")
    runtime_agent_timeout_seconds: float = Field(default=60.0, alias="RUNTIME_AGENT_TIMEOUT")
    runtime_agent_api_mode: str = Field(default="auto", alias="RUNTIME_AGENT_API_MODE")
    market_data_cache_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".cache" / "market_data"),
        alias="MARKET_DATA_CACHE_DIR",
    )
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    cors_allowed_origins: list[str] = Field(
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

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_cors_allowed_origins(cls, value: object) -> object:
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

    @field_validator("runtime_agent_base_url", mode="before")
    @classmethod
    def normalize_runtime_agent_base_url(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized.rstrip("/")

    @field_validator("runtime_agent_api_mode", mode="before")
    @classmethod
    def normalize_runtime_agent_api_mode(cls, value: object) -> str:
        normalized = str(value).strip().lower() if value is not None else "auto"
        if normalized not in {"auto", "responses", "chat_completions"}:
            raise ValueError(
                "RUNTIME_AGENT_API_MODE must be one of: auto, responses, chat_completions"
            )
        return normalized

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
