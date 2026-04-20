from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.agents import get_default_skill_registry
from app.agents.mcp import DefaultMcpConnectionTester
from app.agents.skills import STOCK_ANALYSIS_TOOL_KEYS
from app.core.config import get_settings
from app.core.formatting import decimal_to_string, normalize_symbol
from app.models.agent import Agent
from app.schemas.position import PositionRead
from app.schemas.report import ReportRead
from app.services.market_data_service import MarketDataService
from app.services.mcp_server_service import McpServerService
from app.services.portfolio_service import PortfolioService
from app.services.position_service import PositionService
from app.services.quote_provider import DeterministicQuoteProvider, YahooFinanceQuoteProvider
from app.services.report_service import ReportService
from app.services.skill_service import SkillService


@dataclass(frozen=True)
class StockAnalysisReferenceError(Exception):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


_REQUIRED_TOOL_KEYS_BY_AGENT: dict[str, set[str]] = {
    "financials_analyst": {"ledger.stock_analysis.report_lookup"},
    "news_analyst": {"ledger.stock_analysis.report_lookup"},
    "market_analyst": {"ledger.stock_analysis.market_snapshot"},
    "industry_analyst": {
        "ledger.stock_analysis.market_context",
        "ledger.stock_analysis.price_history",
    },
    "economy_analyst": {"ledger.stock_analysis.market_context"},
    "price_analyst": {"ledger.stock_analysis.price_history"},
    "position_reader": {"ledger.stock_analysis.position_inventory"},
    "history_reader": {"ledger.stock_analysis.price_history"},
    "decision_synthesizer": set(STOCK_ANALYSIS_TOOL_KEYS),
}

_COST_BY_AGENT: dict[str, Decimal] = {
    "financials_analyst": Decimal("0.01000000"),
    "news_analyst": Decimal("0.01000000"),
    "market_analyst": Decimal("0.01000000"),
    "industry_analyst": Decimal("0.01000000"),
    "economy_analyst": Decimal("0.01000000"),
    "price_analyst": Decimal("0.02000000"),
    "position_reader": Decimal("0.01000000"),
    "history_reader": Decimal("0.01000000"),
    "decision_synthesizer": Decimal("0.02000000"),
}

_TOKENS_BY_AGENT: dict[str, int] = {
    "financials_analyst": 12,
    "news_analyst": 12,
    "market_analyst": 14,
    "industry_analyst": 16,
    "economy_analyst": 14,
    "price_analyst": 18,
    "position_reader": 10,
    "history_reader": 12,
    "decision_synthesizer": 20,
}

_DURATION_BY_AGENT: dict[str, int] = {
    key: 10 + index * 3 for index, key in enumerate(_TOKENS_BY_AGENT)
}


class StockAnalysisReferenceService:
    def __init__(self, session: Session) -> None:
        settings = get_settings()
        quote_provider = (
            DeterministicQuoteProvider()
            if settings.quote_provider_backend == "deterministic"
            else YahooFinanceQuoteProvider(timeout=settings.quote_provider_timeout_seconds)
        )
        self.market_data_service = MarketDataService(session, quote_provider)
        self.portfolio_service = PortfolioService(session)
        self.position_service = PositionService(session, quote_provider)
        self.report_service = ReportService(session)
        self.skill_service = SkillService(session, get_default_skill_registry())
        self.mcp_server_service = McpServerService(session, DefaultMcpConnectionTester())

    def maybe_invoke(
        self,
        *,
        agent: Agent,
        resolved_input: dict[str, Any],
        step_index: int,
        slot: str,
    ) -> dict[str, Any] | None:
        del step_index, slot
        if agent.key not in _REQUIRED_TOOL_KEYS_BY_AGENT:
            return None
        self._validate_dependencies(agent)
        output = self._build_output(agent.key, resolved_input)
        return {
            "output": output,
            "tokens": _TOKENS_BY_AGENT[agent.key],
            "costUsd": decimal_to_string(_COST_BY_AGENT[agent.key]),
            "durationMs": _DURATION_BY_AGENT[agent.key],
        }

    def _validate_dependencies(self, agent: Agent) -> None:
        available_tools: set[str] = set()
        for reference in agent.skills:
            resolved = self.skill_service.resolve_toolset_version(
                str(reference["skillKey"]),
                int(reference["skillVersion"]),
            )
            available_tools.update(tool.key for tool in resolved.tools)
        required_tools = _REQUIRED_TOOL_KEYS_BY_AGENT[agent.key]
        missing_tools = sorted(required_tools - available_tools)
        if missing_tools:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=(
                    f"Agent {agent.key!r} is missing required stock-analysis tools: "
                    f"{', '.join(missing_tools)}"
                ),
            )
        if not agent.mcp_servers:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=f"Agent {agent.key!r} is missing an MCP server dependency",
            )
        for reference in agent.mcp_servers:
            boundary = self.mcp_server_service.build_client_boundary_version(
                str(reference["mcpServerKey"]),
                int(reference["mcpServerVersion"]),
                require_enabled=True,
            )
            result = self.mcp_server_service.connection_tester.test(boundary)
            if not result.ok:
                raise StockAnalysisReferenceError(
                    code="agent_execution_missing_dependency",
                    message=(
                        f"Agent {agent.key!r} could not access MCP server "
                        f"{boundary.key!r}: {result.message}"
                    ),
                )

    def _build_output(self, agent_key: str, resolved_input: dict[str, Any]) -> dict[str, Any]:
        if agent_key == "decision_synthesizer":
            return self._build_trading_decision(resolved_input)
        ticker = normalize_symbol(str(resolved_input["ticker"]))
        horizon_days = int(resolved_input["horizon_days"])
        builders = {
            "financials_analyst": self._build_financials_note,
            "news_analyst": self._build_news_note,
            "market_analyst": self._build_market_note,
            "industry_analyst": self._build_industry_note,
            "economy_analyst": self._build_economy_note,
            "price_analyst": self._build_price_note,
            "position_reader": self._build_position_note,
            "history_reader": self._build_history_note,
        }
        return builders[agent_key](ticker=ticker, horizon_days=horizon_days)

    def _build_financials_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        reports = self._reports_for_ticker(ticker)
        if reports:
            latest = reports[0]
            return {
                "summary": (
                    f"Ledger has {len(reports)} persisted report(s) for {ticker}; "
                    f"latest is {latest.slug} over a {horizon_days}d horizon"
                ),
                "signal": "bullish",
            }
        return {
            "summary": (
                f"No persisted Ledger reports were found for {ticker} "
                f"across {horizon_days}d"
            ),
            "signal": "cautious",
        }

    def _build_news_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        reports = self._reports_for_ticker(ticker)
        if reports:
            latest = reports[0]
            tags = ", ".join(latest.metadata.tags[:2]) if latest.metadata.tags else "untagged"
            return {
                "summary": (
                    f"Latest report {latest.slug} for {ticker} carries tags {tags} and feeds the "
                    f"{horizon_days}d news view"
                ),
                "signal": "supportive",
            }
        return {
            "summary": f"No report-backed news context is stored for {ticker} over {horizon_days}d",
            "signal": "cautious",
        }

    def _build_market_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        quote, warnings = self.market_data_service.get_quote_snapshot(ticker)
        if quote is None:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=f"No market snapshot is available for {ticker}: {'; '.join(warnings)}",
            )
        previous_close = quote.previous_close or quote.price
        day_move = ((quote.price - previous_close) / previous_close) * Decimal("100")
        signal = "bullish" if day_move >= Decimal("0") else "cautious"
        return {
            "summary": (
                f"{ticker} trades at {decimal_to_string(quote.price)} {quote.currency} with a "
                f"{self._format_percent(day_move)} daily move for the {horizon_days}d market view"
            ),
            "signal": signal,
        }

    def _build_industry_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        range_value = self._range_for_horizon_days(horizon_days)
        ticker_return = self._history_return(ticker, range_value)
        benchmark_return = self._history_return("^IXIC", range_value)
        relative = ticker_return - benchmark_return
        signal = "bullish" if relative >= Decimal("0") else "cautious"
        return {
            "summary": (
                f"{ticker} is {self._format_percent(relative)} versus NASDAQ on the {range_value} "
                f"industry lens"
            ),
            "signal": signal,
        }

    def _build_economy_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        del ticker, horizon_days
        sp_return = self._history_return("^GSPC", "1mo")
        dow_return = self._history_return("^DJI", "1mo")
        average_return = (sp_return + dow_return) / Decimal("2")
        signal = "supportive" if average_return >= Decimal("0") else "cautious"
        return {
            "summary": (
                f"Macro context averages {self._format_percent(average_return)} across S&P 500 and "
                "Dow Jones over the past month"
            ),
            "signal": signal,
        }

    def _build_price_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        range_value = self._range_for_horizon_days(horizon_days)
        history = self.market_data_service.get_history_snapshot(ticker, range_value)
        if not history.series:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=f"No price history is available for {ticker} over {range_value}",
            )
        series = history.series[0]
        first_close = series.points[0].close
        last_close = series.points[-1].close
        trend = ((last_close - first_close) / first_close) * Decimal("100")
        signal = "bullish" if trend >= Decimal("0") else "cautious"
        return {
            "summary": (
                f"{ticker} moved {self._format_percent(trend)} across "
                f"{len(series.points)} history points in the {range_value} price view"
            ),
            "signal": signal,
        }

    def _build_position_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        del horizon_days
        portfolios = {item.id: item for item in self.portfolio_service.list_portfolios()}
        matched_positions: list[PositionRead] = []
        for portfolio in portfolios.values():
            matched_positions.extend(
                position
                for position in self.position_service.list_positions(portfolio.id)
                if position.symbol == ticker
            )
        if not matched_positions:
            return {
                "summary": f"No Ledger portfolio currently holds {ticker}",
                "signal": "cautious",
            }
        total_quantity = sum((position.quantity for position in matched_positions), Decimal("0"))
        slugs = sorted({portfolios[position.portfolio_id].slug for position in matched_positions})
        return {
            "summary": (
                f"{ticker} is held across {', '.join(slugs)} with total quantity "
                f"{decimal_to_string(total_quantity)}"
            ),
            "signal": "supportive",
        }

    def _build_history_note(self, *, ticker: str, horizon_days: int) -> dict[str, str]:
        range_value = self._range_for_horizon_days(horizon_days)
        history = self.market_data_service.get_history_snapshot(ticker, range_value)
        if not history.series:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=f"No historical series is available for {ticker} over {range_value}",
            )
        series = history.series[0]
        lows = min(point.close for point in series.points)
        highs = max(point.close for point in series.points)
        return {
            "summary": (
                f"{ticker} history spans {len(series.points)} points with a range from "
                f"{decimal_to_string(lows)} to {decimal_to_string(highs)}"
            ),
            "signal": "supportive",
        }

    def _build_trading_decision(self, analyses: dict[str, Any]) -> dict[str, Any]:
        bullish_votes = sum(
            1
            for value in analyses.values()
            if isinstance(value, dict) and value.get("signal") in {"bullish", "supportive"}
        )
        action = "buy" if bullish_votes >= 5 else "hold"
        ordered_summaries = [
            str(value["summary"])
            for key, value in sorted(analyses.items())
            if isinstance(value, dict) and "summary" in value
        ]
        return {
            "action": action,
            "confidence": 0.84 if action == "buy" else 0.61,
            "rationale": " | ".join(ordered_summaries),
            "price_targets": [118.0, 126.0] if action == "buy" else [104.0, 110.0],
            "risks": ["report coverage can lag", "macro reversal risk"],
        }

    def _reports_for_ticker(self, ticker: str) -> list[ReportRead]:
        return self.report_service.list_reports(ticker=ticker, limit=5)

    def _history_return(self, symbol: str, range_value: str) -> Decimal:
        history = self.market_data_service.get_history_snapshot(symbol, range_value)
        if not history.series:
            raise StockAnalysisReferenceError(
                code="agent_execution_missing_dependency",
                message=f"No benchmark history is available for {symbol} over {range_value}",
            )
        series = history.series[0]
        first_close = series.points[0].close
        last_close = series.points[-1].close
        return ((last_close - first_close) / first_close) * Decimal("100")

    @staticmethod
    def _range_for_horizon_days(horizon_days: int) -> str:
        if horizon_days <= 30:
            return "1mo"
        if horizon_days <= 90:
            return "3mo"
        if horizon_days <= 366:
            return "1y"
        return "max"

    @staticmethod
    def _format_percent(value: Decimal) -> str:
        quantized = value.quantize(Decimal("0.01"))
        prefix = "+" if quantized >= Decimal("0") else ""
        return f"{prefix}{quantized}%"


__all__ = ["StockAnalysisReferenceError", "StockAnalysisReferenceService"]
