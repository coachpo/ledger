"""Neutral provider-bundle bridge for platform execution services."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.execution_providers import ExecutionProviderBundle
from app.services.extension_service import ExtensionService
from app.services.quote_provider import QuoteProvider


def get_platform_execution_provider_bundle(session: Session) -> ExecutionProviderBundle:
    return ExtensionService(session).get_execution_provider_bundle()


def get_platform_quote_provider(session: Session) -> QuoteProvider | None:
    return get_platform_execution_provider_bundle(session).quote_provider


__all__ = [
    "get_platform_execution_provider_bundle",
    "get_platform_quote_provider",
]
