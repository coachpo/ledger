from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_DATABASE_URL = "postgresql+psycopg://signaldeck:signaldeck@localhost:25432/signaldeck"
DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY = "signaldeck-agent-platform-dev-key"
PRODUCTION_RUNTIME_MODES = {"production", "prod", "staging"}
PLACEHOLDER_AGENT_PLATFORM_ENCRYPTION_KEYS = {
    DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
    "change-me",
    "changeme",
}
_FINANCE_NEWS_PROVIDER_KEYS = {"alpha_vantage", "deterministic", "yahoo"}


class Settings(BaseSettings):
    runtime_mode: Literal["local", "development", "test", "staging", "production", "prod"] = Field(
        default="local",
        alias="SIGNALDECK_RUNTIME_MODE",
    )
    database_url: str = Field(
        default=DEFAULT_DATABASE_URL,
        alias="DATABASE_URL",
    )
    quote_provider_timeout_seconds: float = Field(default=5.0, alias="QUOTE_PROVIDER_TIMEOUT")
    quote_provider_backend: str = Field(default="yahoo", alias="QUOTE_PROVIDER_BACKEND")
    quote_stale_after_minutes: int = Field(default=15, alias="QUOTE_STALE_AFTER_MINUTES")
    finance_news_provider_order: Annotated[list[str], NoDecode] = Field(
        default=["yahoo"],
        alias="FINANCE_NEWS_PROVIDER_ORDER",
    )
    finance_global_news_queries: Annotated[list[str], NoDecode] = Field(
        default=[
            "financial markets",
            "macro economy",
            "monetary policy",
        ],
        alias="FINANCE_GLOBAL_NEWS_QUERIES",
    )
    finance_global_news_lookback_days: int = Field(
        default=7,
        alias="FINANCE_GLOBAL_NEWS_LOOKBACK_DAYS",
        ge=1,
    )
    finance_reddit_subreddits: Annotated[list[str], NoDecode] = Field(
        default=["wallstreetbets", "stocks", "investing"],
        alias="FINANCE_REDDIT_SUBREDDITS",
    )
    finance_reddit_retry_after_max_seconds: float = Field(
        default=2.0,
        alias="FINANCE_REDDIT_RETRY_AFTER_MAX_SECONDS",
        ge=0,
    )
    finance_reddit_inter_request_delay_seconds: float = Field(
        default=0.0,
        alias="FINANCE_REDDIT_INTER_REQUEST_DELAY_SECONDS",
        ge=0,
    )
    digital_oracle_prediction_markets_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_PREDICTION_MARKETS_ENABLED",
    )
    digital_oracle_sec_filings_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_SEC_FILINGS_ENABLED",
    )
    digital_oracle_market_sentiment_enabled: bool = Field(
        default=True,
        alias="DIGITAL_ORACLE_MARKET_SENTIMENT_ENABLED",
    )
    digital_oracle_macro_rates_enabled: bool = Field(
        default=True, alias="DIGITAL_ORACLE_MACRO_RATES_ENABLED"
    )
    digital_oracle_crypto_derivatives_enabled: bool = Field(
        default=True, alias="DIGITAL_ORACLE_CRYPTO_DERIVATIVES_ENABLED"
    )
    digital_oracle_cftc_positioning_enabled: bool = Field(
        default=True, alias="DIGITAL_ORACLE_CFTC_POSITIONING_ENABLED"
    )
    digital_oracle_options_enabled: bool = Field(
        default=True, alias="DIGITAL_ORACLE_OPTIONS_ENABLED"
    )
    digital_oracle_prediction_markets_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_PREDICTION_MARKETS_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=20,
    )
    digital_oracle_sec_filings_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_SEC_FILINGS_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    digital_oracle_macro_rates_default_item_limit: int = Field(
        default=10, alias="DIGITAL_ORACLE_MACRO_RATES_DEFAULT_ITEM_LIMIT", ge=1, le=50
    )
    digital_oracle_crypto_derivatives_default_item_limit: int = Field(
        default=10,
        alias="DIGITAL_ORACLE_CRYPTO_DERIVATIVES_DEFAULT_ITEM_LIMIT",
        ge=1,
        le=50,
    )
    digital_oracle_cftc_positioning_default_item_limit: int = Field(
        default=10, alias="DIGITAL_ORACLE_CFTC_POSITIONING_DEFAULT_ITEM_LIMIT", ge=1, le=50
    )
    digital_oracle_options_default_item_limit: int = Field(
        default=10, alias="DIGITAL_ORACLE_OPTIONS_DEFAULT_ITEM_LIMIT", ge=1, le=50
    )
    agent_platform_encryption_key: str = Field(
        default=DEFAULT_AGENT_PLATFORM_ENCRYPTION_KEY,
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
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        alias="CORS_ALLOWED_ORIGINS",
    )

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "cors_allowed_origins",
        "mcp_stdio_allowed_commands",
        "http_operation_allowed_methods",
        "finance_news_provider_order",
        "finance_global_news_queries",
        "finance_reddit_subreddits",
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

    @field_validator("finance_news_provider_order")
    @classmethod
    def normalize_finance_news_provider_order(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            provider_key = item.strip().lower()
            if not provider_key or provider_key in seen:
                continue
            if provider_key not in _FINANCE_NEWS_PROVIDER_KEYS:
                allowed = ", ".join(sorted(_FINANCE_NEWS_PROVIDER_KEYS))
                raise ValueError(f"FINANCE_NEWS_PROVIDER_ORDER must contain only: {allowed}")
            seen.add(provider_key)
            normalized.append(provider_key)
        if not normalized:
            raise ValueError("FINANCE_NEWS_PROVIDER_ORDER must include at least one provider")
        return normalized

    @field_validator("finance_global_news_queries", "finance_reddit_subreddits")
    @classmethod
    def normalize_deduped_finance_list(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            entry = item.strip()
            if not entry or entry in seen:
                continue
            seen.add(entry)
            normalized.append(entry)
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

    @field_validator("runtime_mode", mode="before")
    @classmethod
    def normalize_runtime_mode(cls, value: object) -> object:
        if value is None:
            return value
        return str(value).strip().lower()

    @field_validator("agent_platform_encryption_key", mode="before")
    @classmethod
    def normalize_agent_platform_encryption_key(cls, value: object) -> str:
        return str(value).strip() if value is not None else ""

    @field_validator("quote_provider_backend", mode="before")
    @classmethod
    def normalize_quote_provider_backend(cls, value: object) -> str:
        normalized = str(value).strip().lower() if value is not None else "yahoo"
        if normalized not in {"yahoo", "deterministic"}:
            raise ValueError("QUOTE_PROVIDER_BACKEND must be one of: yahoo, deterministic")
        return normalized

    @model_validator(mode="after")
    def validate_production_runtime_config(self) -> Settings:
        if self.runtime_mode not in PRODUCTION_RUNTIME_MODES:
            return self

        if "database_url" not in self.model_fields_set or self.database_url == DEFAULT_DATABASE_URL:
            raise ValueError(
                "DATABASE_URL must be explicitly configured in production runtime mode"
            )

        if (
            "agent_platform_encryption_key" not in self.model_fields_set
            or self.agent_platform_encryption_key in PLACEHOLDER_AGENT_PLATFORM_ENCRYPTION_KEYS
        ):
            message = (
                "AGENT_PLATFORM_ENCRYPTION_KEY must be explicitly configured to a non-placeholder "
                "value in production runtime mode"
            )
            raise ValueError(message)

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
