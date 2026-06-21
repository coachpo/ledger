from __future__ import annotations

from functools import lru_cache
from typing import Annotated, ClassVar, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_FINANCE_NEWS_PROVIDER_KEYS = {"alpha_vantage", "deterministic", "yahoo"}


class FinanceWorkspaceSettings(BaseSettings):
    quote_provider_timeout_seconds: float = Field(default=5.0, alias="QUOTE_PROVIDER_TIMEOUT")
    quote_provider_backend: Literal["yahoo", "deterministic"] = Field(
        default="yahoo",
        alias="QUOTE_PROVIDER_BACKEND",
    )
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

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "finance_news_provider_order",
        "finance_global_news_queries",
        "finance_reddit_subreddits",
        mode="before",
    )
    @classmethod
    def split_string_lists(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

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

    @field_validator("quote_provider_backend", mode="before")
    @classmethod
    def normalize_quote_provider_backend(cls, value: str | None) -> str:
        normalized = value.strip().lower() if value is not None else "yahoo"
        if normalized not in {"yahoo", "deterministic"}:
            raise ValueError("QUOTE_PROVIDER_BACKEND must be one of: yahoo, deterministic")
        return normalized


@lru_cache
def get_finance_workspace_settings() -> FinanceWorkspaceSettings:
    return FinanceWorkspaceSettings()


def reset_finance_workspace_settings_cache() -> None:
    get_finance_workspace_settings.cache_clear()


__all__ = [
    "FinanceWorkspaceSettings",
    "get_finance_workspace_settings",
    "reset_finance_workspace_settings_cache",
]
