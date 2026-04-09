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
    quote_stale_after_minutes: int = Field(default=15, alias="QUOTE_STALE_AFTER_MINUTES")
    backtest_test_mode: bool = Field(default=False, alias="BACKTEST_TEST_MODE")
    backtest_agent_model: str = Field(default="gpt-4.1-mini", alias="BACKTEST_AGENT_MODEL")
    backtest_agent_base_url: str | None = Field(default=None, alias="BACKTEST_AGENT_BASE_URL")
    backtest_agent_api_key: str | None = Field(default=None, alias="BACKTEST_AGENT_API_KEY")
    backtest_agent_temperature: float = Field(default=0.0, alias="BACKTEST_AGENT_TEMPERATURE")
    backtest_agent_timeout_seconds: float = Field(default=60.0, alias="BACKTEST_AGENT_TIMEOUT")
    backtest_agent_api_mode: str = Field(default="auto", alias="BACKTEST_AGENT_API_MODE")
    market_data_cache_dir: str = Field(
        default=str(Path(__file__).resolve().parents[2] / ".cache" / "market_data"),
        alias="MARKET_DATA_CACHE_DIR",
    )
    public_base_url: str | None = Field(default=None, alias="PUBLIC_BASE_URL")
    cors_allowed_origins: list[str] = Field(
        default=[
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

    @field_validator("backtest_agent_base_url", mode="before")
    @classmethod
    def normalize_backtest_agent_base_url(cls, value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        return normalized.rstrip("/")

    @field_validator("backtest_agent_api_mode", mode="before")
    @classmethod
    def normalize_backtest_agent_api_mode(cls, value: object) -> str:
        normalized = str(value).strip().lower() if value is not None else "auto"
        if normalized not in {"auto", "responses", "chat_completions"}:
            raise ValueError(
                "BACKTEST_AGENT_API_MODE must be one of: auto, responses, chat_completions"
            )
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
