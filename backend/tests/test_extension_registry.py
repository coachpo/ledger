from __future__ import annotations

import pytest

from app.extensions.registry import BundledExtensionRegistry, get_bundled_extension_registry
from app.extensions.signaldeck_finance.ownership import FINANCE_WORKSPACE_EXTENSION_KEY


def test_bundled_extension_registry_discovers_finance_workspace_once() -> None:
    registry = get_bundled_extension_registry()

    extensions = registry.list_extensions()
    assert len(extensions) == 1
    extension = extensions[0]
    assert extension.key == FINANCE_WORKSPACE_EXTENSION_KEY
    assert extension.label == "Finance Workspace"
    assert extension.default_enabled is True
    assert registry.get_extension(FINANCE_WORKSPACE_EXTENSION_KEY) is extension
    assert {contribution.surface for contribution in registry.list_api_router_contributions()} == {
        "/api/v1/portfolios",
        "/api/v1/portfolios/{portfolio_id}/balances",
        "/api/v1/portfolios/{portfolio_id}/positions",
        "/api/v1/portfolios/{portfolio_id}/trading-operations",
        "/api/v1/portfolios/{portfolio_id}/market-data",
        "/api/v1/templates",
        "/api/v1/reports",
    }
    expected_tool_keys = {
        "signaldeck.fundamentals.lookup",
        "signaldeck.indicators.lookup",
        "signaldeck.insider_data.lookup",
        "signaldeck.market_data.history_lookup",
        "signaldeck.market_data.ohlcv_lookup",
        "signaldeck.market_data.quote_lookup",
        "signaldeck.market_sentiment.lookup",
        "signaldeck.news.lookup",
        "signaldeck.positions.lookup",
        "signaldeck.prediction_markets.lookup",
        "signaldeck.reports.lookup",
        "signaldeck.sec_filings.lookup",
        "signaldeck.social_sentiment.lookup",
    }
    server_tool_keys = {
        contribution.key for contribution in registry.list_server_declared_tool_contributions()
    }
    runtime_tool_keys = {
        contribution.key for contribution in registry.list_runtime_tool_contributions()
    }
    assert server_tool_keys == expected_tool_keys
    assert runtime_tool_keys == expected_tool_keys


def test_bundled_extension_registry_rejects_duplicate_keys() -> None:
    extension = get_bundled_extension_registry().require_extension(FINANCE_WORKSPACE_EXTENSION_KEY)

    with pytest.raises(ValueError, match="Duplicate bundled extension key"):
        _ = BundledExtensionRegistry((extension, extension))
