from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.formatting import decimal_to_string, portfolio_cash_total, to_utc
from app.models.balance import Balance
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.report import Report
from app.repositories.balance import BalanceRepository
from app.repositories.portfolio import PortfolioRepository
from app.repositories.position import PositionRepository
from app.repositories.report import ReportRepository
from app.schemas.market_data import MarketQuoteRead

if TYPE_CHECKING:
    from app.services.market_data_service import MarketDataService

_PLACEHOLDER_RE = re.compile(r"\{\{(.+?)\}\}")
_INPUT_REFERENCE_RE = re.compile(r"^inputs\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)$")
_REPORT_LATEST_RE = re.compile(
    r"^\.latest(?:\(\s*(?P<argument>.*?)\s*\))?(?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$"
)
_REPORT_INDEX_RE = re.compile(r"^\[(?P<index>\d+)\](?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$")
_REPORT_BY_TAG_LATEST_RE = re.compile(
    r"^\.by_tag\(\s*(?P<argument>.*?)\s*\)\.latest(?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$"
)
_PORTFOLIO_BY_SLUG_RE = re.compile(r"^\.by_slug\(\s*(?P<argument>.*?)\s*\)(?P<rest>(?:\..+)?)$")
_POSITION_BY_SYMBOL_RE = re.compile(
    r"^\.positions\.by_symbol\(\s*(?P<argument>.*?)\s*\)(?:\.(?P<field>[A-Za-z_][A-Za-z0-9_]*))?$"
)

_PORTFOLIO_SCALAR_FIELDS = frozenset(
    {
        "name",
        "slug",
        "description",
        "base_currency",
        "position_count",
        "balance_count",
        "created_at",
        "updated_at",
    }
)

_BALANCE_SCALAR_FIELDS = frozenset(
    {
        "label",
        "amount",
        "operation_type",
        "currency",
    }
)

_POSITION_SCALAR_FIELDS = frozenset(
    {
        "symbol",
        "name",
        "quantity",
        "average_cost",
        "currency",
    }
)

_PORTFOLIO_METRIC_FIELDS = frozenset(
    {
        "total_value",
        "unrealized_pnl",
    }
)

_POSITION_METRIC_FIELDS = frozenset(
    {
        "market_value",
        "unrealized_pnl",
        "unrealized_pnl_percent",
    }
)

_REPORT_SCALAR_FIELDS = frozenset({"name", "created_at"})


@dataclass(slots=True)
class ReportSelection:
    matched: bool
    report: Report | None
    field: str | None = None
    report_name: str | None = None
    error: str | None = None


@dataclass(slots=True)
class PortfolioSelection:
    matched: bool
    portfolio: Portfolio | None
    remaining: str = ""
    error: str | None = None


class TemplateCompilerService:
    def __init__(
        self, session: Session, market_data_service: MarketDataService | None = None
    ) -> None:
        self.session = session
        self.portfolio_repo = PortfolioRepository(session)
        self.balance_repo = BalanceRepository(session)
        self.position_repo = PositionRepository(session)
        self.report_repo = ReportRepository(session)
        self.market_data_service = market_data_service
        self._quote_cache: dict[int, dict[str, MarketQuoteRead]] = {}
        self._report_resolve_stack: set[str] = set()
        self._inputs: dict[str, str] = {}

    def compile(self, content: str, inputs: dict[str, str] | None = None) -> str:
        self._quote_cache = {}
        self._report_resolve_stack = set()
        self._inputs = inputs or {}

        def replacer(match: re.Match[str]) -> str:
            path = match.group(1).strip()
            return self._resolve(path)

        return _PLACEHOLDER_RE.sub(replacer, content)

    def get_placeholder_tree(self) -> dict[str, list[dict[str, object]]]:
        portfolios = self.portfolio_repo.list_all()
        portfolio_result: list[dict[str, object]] = []
        for portfolio in portfolios:
            positions = self.position_repo.list_for_portfolio(portfolio.id)
            portfolio_result.append(
                {
                    "slug": portfolio.slug,
                    "name": portfolio.name,
                    "base_currency": portfolio.base_currency,
                    "positions": [{"symbol": p.symbol, "name": p.name} for p in positions],
                }
            )

        reports = self.report_repo.list_all()
        report_result: list[dict[str, object]] = []
        for report in reports:
            report_result.append(
                {
                    "name": report.name,
                    "created_at": report.created_at,
                }
            )

        return {"portfolios": portfolio_result, "reports": report_result}

    def _resolve(self, path: str) -> str:
        if path == "inputs" or path.startswith("inputs."):
            return self._resolve_inputs(path)

        if path == "portfolios" or path.startswith("portfolios.by_slug("):
            return self._resolve_portfolios_path(path)

        if path == "reports" or path.startswith("reports.") or path.startswith("reports["):
            return self._resolve_reports_path(path)

        parts = [p.strip() for p in path.split(".")]
        if not parts:
            return "[Unknown root: ]"

        root = parts[0]

        if root == "portfolios":
            return self._resolve_portfolios(parts)

        return f"[Unknown root: {root}]"

    def _resolve_inputs(self, path: str) -> str:
        if path == "inputs":
            return self._render_all_inputs()

        match = _INPUT_REFERENCE_RE.fullmatch(path)
        if match is None:
            return f"[Unknown input: {path}]"

        input_name = match.group("name")
        value = self._inputs.get(input_name)
        if value is None:
            return f"[Missing input: {input_name}]"

        return value

    def _render_all_inputs(self) -> str:
        if not self._inputs:
            return "*(no inputs)*"
        return "\n".join(f"- {key}: {value}" for key, value in sorted(self._inputs.items()))

    def _resolve_portfolios(self, parts: list[str]) -> str:
        if len(parts) == 1:
            return self._render_all_portfolios()

        slug = parts[1]
        portfolio = self.portfolio_repo.get_by_slug(slug)
        if portfolio is None:
            return f"[Unknown portfolio: {slug}]"

        return self._resolve_portfolio_remaining(portfolio, parts[2:])

    def _resolve_portfolios_path(self, path: str) -> str:
        if path == "portfolios":
            return self._render_all_portfolios()

        suffix = path[len("portfolios") :]
        dynamic_selection = self._parse_dynamic_portfolio_selector(suffix)
        if dynamic_selection.matched:
            return self._render_portfolio_selection(dynamic_selection)

        return self._resolve_portfolios([p.strip() for p in path.split(".")])

    def _parse_dynamic_portfolio_selector(self, suffix: str) -> PortfolioSelection:
        match = _PORTFOLIO_BY_SLUG_RE.fullmatch(suffix)
        if match is None:
            return PortfolioSelection(matched=False, portfolio=None)

        slug, error = self._resolve_argument(match.group("argument"))
        if error is not None:
            return PortfolioSelection(matched=True, portfolio=None, error=error)
        if slug is None:
            return PortfolioSelection(
                matched=True, portfolio=None, error="[Invalid selector argument: ]"
            )

        resolved_slug = slug
        portfolio = self.portfolio_repo.get_by_slug(resolved_slug)
        return PortfolioSelection(
            matched=True,
            portfolio=portfolio,
            remaining=match.group("rest") or "",
        )

    def _render_portfolio_selection(self, selection: PortfolioSelection) -> str:
        if selection.error is not None:
            return selection.error

        if selection.portfolio is None:
            return ""

        if not selection.remaining:
            return self._render_portfolio_summary(selection.portfolio)

        position_selection = self._parse_dynamic_position_selector(
            selection.portfolio, selection.remaining
        )
        if position_selection is not None:
            return position_selection

        remaining = (
            selection.remaining[1:].split(".") if selection.remaining.startswith(".") else []
        )
        return self._resolve_portfolio_remaining(selection.portfolio, remaining)

    def _parse_dynamic_position_selector(self, portfolio: Portfolio, remainder: str) -> str | None:
        match = _POSITION_BY_SYMBOL_RE.fullmatch(remainder)
        if match is None:
            return None

        symbol, error = self._resolve_argument(match.group("argument"))
        if error is not None:
            return error
        if symbol is None:
            return "[Invalid selector argument: ]"

        resolved_symbol = symbol.upper()

        position = next(
            (
                candidate
                for candidate in self.position_repo.list_for_portfolio(portfolio.id)
                if candidate.symbol == resolved_symbol
            ),
            None,
        )
        if position is None:
            return ""

        field = match.group("field")
        if field is None:
            return self._render_position_line(position)
        if field in _POSITION_SCALAR_FIELDS:
            return self._format_value(getattr(position, field, None))
        if field in _POSITION_METRIC_FIELDS:
            return self._resolve_position_metric(position, portfolio, field)
        return f"[Unknown position field: {field}]"

    def _resolve_portfolio_remaining(self, portfolio: Portfolio, remaining: list[str]) -> str:
        if not remaining:
            return self._render_portfolio_summary(portfolio)

        field = remaining[0]

        if field in _PORTFOLIO_SCALAR_FIELDS:
            return self._get_portfolio_scalar(portfolio, field)

        if field in _PORTFOLIO_METRIC_FIELDS:
            return self._resolve_portfolio_metric(portfolio, field)

        if field == "balance":
            return self._resolve_balance(portfolio, remaining[1:])

        if field == "positions":
            return self._resolve_positions(portfolio, remaining[1:])

        return f"[Unknown field: {field}]"

    def _resolve_reports_path(self, path: str) -> str:
        if path == "reports":
            return self._render_all_reports()

        suffix = path[len("reports") :]

        dynamic_selection = self._parse_dynamic_report_selector(suffix)
        if dynamic_selection.matched:
            return self._render_report_selection(dynamic_selection, dynamic=True)

        exact_selection = self._parse_exact_report_selector(suffix)
        if exact_selection.matched:
            if exact_selection.report is None and self._looks_like_dynamic_report_selector(suffix):
                return f"[Invalid report selector: {path}]"
            return self._render_report_selection(exact_selection, dynamic=False)

        return f"[Invalid report selector: {path}]"

    @staticmethod
    def _looks_like_dynamic_report_selector(suffix: str) -> bool:
        return (
            suffix.startswith(".latest") or suffix.startswith(".by_tag(") or suffix.startswith("[")
        )

    def _parse_dynamic_report_selector(self, suffix: str) -> ReportSelection:
        latest_match = _REPORT_LATEST_RE.fullmatch(suffix)
        if latest_match is not None:
            field = latest_match.group("field")
            argument = latest_match.group("argument")
            ticker, error = self._resolve_argument(argument)
            if error is not None:
                return ReportSelection(matched=True, report=None, field=field, error=error)
            if ticker is None and argument is not None:
                return ReportSelection(
                    matched=True,
                    report=None,
                    field=field,
                    error="[Invalid selector argument: ]",
                )
            normalized_ticker = ticker.upper() if ticker is not None else None
            reports = self.report_repo.list_all(ticker=normalized_ticker, limit=1)
            report = reports[0] if reports else None
            return ReportSelection(matched=True, report=report, field=field, error=error)

        index_match = _REPORT_INDEX_RE.fullmatch(suffix)
        if index_match is not None:
            field = index_match.group("field")
            index = int(index_match.group("index"))
            reports = self.report_repo.list_all(limit=1, offset=index)
            report = reports[0] if reports else None
            return ReportSelection(matched=True, report=report, field=field)

        by_tag_latest_match = _REPORT_BY_TAG_LATEST_RE.fullmatch(suffix)
        if by_tag_latest_match is not None:
            field = by_tag_latest_match.group("field")
            tag, error = self._resolve_argument(by_tag_latest_match.group("argument"))
            if error is not None:
                return ReportSelection(matched=True, report=None, field=field, error=error)
            if tag is None:
                return ReportSelection(
                    matched=True,
                    report=None,
                    field=field,
                    error="[Invalid selector argument: ]",
                )
            reports = self.report_repo.list_all(tag=tag, limit=1)
            report = reports[0] if reports else None
            return ReportSelection(matched=True, report=report, field=field)

        return ReportSelection(matched=False, report=None)

    def _parse_exact_report_selector(self, suffix: str) -> ReportSelection:
        if not suffix.startswith("."):
            return ReportSelection(matched=False, report=None)

        remainder = suffix[1:]
        if not remainder:
            return ReportSelection(matched=False, report=None)

        name, has_field_separator, field = remainder.partition(".")
        if not name:
            return ReportSelection(matched=False, report=None)

        report = self.report_repo.get_by_name(name)
        return ReportSelection(
            matched=True,
            report=report,
            field=field if has_field_separator else None,
            report_name=name,
        )

    def _render_report_selection(self, selection: ReportSelection, *, dynamic: bool) -> str:
        if selection.error is not None:
            return selection.error

        report = selection.report
        if report is None:
            if dynamic:
                return ""
            missing_name = selection.report_name or ""
            return f"[Unknown report: {missing_name}]"

        field = selection.field
        if field is None:
            return self._render_report_metadata(report)

        if field == "content":
            return self._resolve_report_content(report)

        if field in _REPORT_SCALAR_FIELDS:
            return self._format_value(getattr(report, field, None))

        return f"[Unknown report field: {field}]"

    def _resolve_argument(self, argument: str | None) -> tuple[str | None, str | None]:
        if argument is None:
            return None, None

        trimmed = argument.strip()
        if not trimmed:
            return None, "[Invalid selector argument: ]"

        if len(trimmed) >= 2 and trimmed.startswith('"') and trimmed.endswith('"'):
            value = trimmed[1:-1].strip()
            if not value:
                return None, "[Invalid selector argument: ]"
            return value, None

        input_match = _INPUT_REFERENCE_RE.fullmatch(trimmed)
        if input_match is None:
            return None, f"[Invalid selector argument: {trimmed}]"

        input_name = input_match.group("name")
        input_value = self._inputs.get(input_name)
        if input_value is None:
            return None, f"[Missing input: {input_name}]"

        return input_value, None

    def _render_all_reports(self) -> str:
        reports = self.report_repo.list_all()
        if not reports:
            return "*(no reports)*"
        lines: list[str] = []
        for report in reports:
            lines.append(f"- {self._render_report_metadata(report)}")
        return "\n".join(lines)

    def _render_report_metadata(self, report: Report) -> str:
        created = self._format_value(report.created_at)
        return f"**{report.name}** ({created})"

    def _resolve_report_content(self, report: Report) -> str:
        if report.name in self._report_resolve_stack:
            return f"[Circular report reference: {report.name}]"

        self._report_resolve_stack.add(report.name)
        try:
            compiled = _PLACEHOLDER_RE.sub(
                lambda match: self._resolve(match.group(1).strip()),
                report.content,
            )
            return compiled
        finally:
            self._report_resolve_stack.discard(report.name)

    def _render_all_portfolios(self) -> str:
        portfolios = self.portfolio_repo.list_all()
        if not portfolios:
            return "*(no portfolios)*"
        sections: list[str] = []
        for portfolio in portfolios:
            sections.append(f"## {portfolio.name}\n\n{self._render_portfolio_summary(portfolio)}")
        return "\n\n".join(sections)

    def _render_portfolio_summary(self, portfolio: Portfolio) -> str:
        position_count = self.portfolio_repo.count_positions(portfolio.id)
        balance_count = self.portfolio_repo.count_balances(portfolio.id)
        desc = portfolio.description or ""
        lines = [
            f"**{portfolio.name}** ({portfolio.base_currency})",
        ]
        if desc:
            lines.append(desc)
        lines.append(f"Positions: {position_count} | Balances: {balance_count}")
        return "\n".join(lines)

    def _get_portfolio_scalar(self, portfolio: Portfolio, field: str) -> str:
        if field == "position_count":
            return str(self.portfolio_repo.count_positions(portfolio.id))
        if field == "balance_count":
            return str(self.portfolio_repo.count_balances(portfolio.id))
        value = getattr(portfolio, field, None)
        return self._format_value(value)

    def _resolve_balance(self, portfolio: Portfolio, remaining: list[str]) -> str:
        balances = self.balance_repo.list_for_portfolio(portfolio.id)
        available = self._compute_available_balance(balances, portfolio.base_currency)

        if not remaining:
            return self._render_available_balance(available)

        field = remaining[0]
        if field in _BALANCE_SCALAR_FIELDS:
            return self._format_value(available.get(field))

        return f"[Unknown balance field: {field}]"

    def _compute_available_balance(
        self, balances: list[Balance], currency: str
    ) -> dict[str, object]:
        total = self._compute_signed_balance_total(balances)
        return {
            "label": "Available Balance",
            "amount": total,
            "operation_type": "DEPOSIT" if total >= 0 else "WITHDRAWAL",
            "currency": currency,
        }

    def _render_available_balance(self, available: dict[str, object]) -> str:
        amount = available["amount"]
        currency = available["currency"]
        return f"{self._format_value(amount)} {currency}"

    def _resolve_positions(self, portfolio: Portfolio, remaining: list[str]) -> str:
        positions = self.position_repo.list_for_portfolio(portfolio.id)

        if not remaining:
            return self._render_positions_list(positions)

        symbol = remaining[0].upper()
        position = next((p for p in positions if p.symbol == symbol), None)
        if position is None:
            return f"[Unknown position: {symbol}]"

        if len(remaining) == 1:
            return self._render_position_line(position)

        field = remaining[1]
        if field in _POSITION_SCALAR_FIELDS:
            return self._format_value(getattr(position, field, None))

        if field in _POSITION_METRIC_FIELDS:
            return self._resolve_position_metric(position, portfolio, field)

        return f"[Unknown position field: {field}]"

    def _render_positions_list(self, positions: list[Position]) -> str:
        if not positions:
            return "- *(none)*"
        lines: list[str] = []
        for position in positions:
            lines.append(f"- {self._render_position_line(position)}")
        return "\n".join(lines)

    def _render_position_line(self, position: Position) -> str:
        name_part = f" ({position.name})" if position.name else ""
        quantity = decimal_to_string(position.quantity)
        avg_cost = decimal_to_string(position.average_cost)
        return f"{position.symbol}{name_part}: {quantity} shares @ {avg_cost} {position.currency}"

    def _format_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return decimal_to_string(value)
        from datetime import datetime

        if isinstance(value, datetime):
            return to_utc(value).isoformat().replace("+00:00", "Z")
        return str(value)

    def _get_quotes_for_portfolio(self, portfolio: Portfolio) -> dict[str, MarketQuoteRead]:
        if portfolio.id in self._quote_cache:
            return self._quote_cache[portfolio.id]

        if self.market_data_service is None:
            self._quote_cache[portfolio.id] = {}
            return self._quote_cache[portfolio.id]

        positions = self.position_repo.list_for_portfolio(portfolio.id)
        symbols = [p.symbol for p in positions]
        if not symbols:
            self._quote_cache[portfolio.id] = {}
            return self._quote_cache[portfolio.id]

        result = self.market_data_service.get_quotes(portfolio.id, symbols)
        quotes_by_symbol: dict[str, MarketQuoteRead] = {}
        for quote in result.quotes:
            quotes_by_symbol[quote.symbol] = quote

        self._quote_cache[portfolio.id] = quotes_by_symbol
        return quotes_by_symbol

    def _compute_signed_balance_total(self, balances: list[Balance]) -> Decimal:
        return portfolio_cash_total(balances)

    def _resolve_portfolio_metric(self, portfolio: Portfolio, field: str) -> str:
        quotes = self._get_quotes_for_portfolio(portfolio)
        positions = self.position_repo.list_for_portfolio(portfolio.id)

        if field == "total_value":
            return self._compute_portfolio_total_value(portfolio, positions, quotes)

        if field == "unrealized_pnl":
            return self._compute_portfolio_unrealized_pnl(positions, quotes)

        return ""

    def _compute_portfolio_total_value(
        self,
        portfolio: Portfolio,
        positions: list[Position],
        quotes: dict[str, MarketQuoteRead],
    ) -> str:
        market_value_sum = Decimal("0")
        for position in positions:
            quote = quotes.get(position.symbol)
            if quote is None:
                return ""
            market_value_sum += position.quantity * quote.price

        balances = self.balance_repo.list_for_portfolio(portfolio.id)
        balance_total = self._compute_signed_balance_total(balances)
        total = market_value_sum + balance_total
        return decimal_to_string(total)

    def _compute_portfolio_unrealized_pnl(
        self,
        positions: list[Position],
        quotes: dict[str, MarketQuoteRead],
    ) -> str:
        pnl_sum = Decimal("0")
        for position in positions:
            quote = quotes.get(position.symbol)
            if quote is None:
                return ""
            pnl_sum += (quote.price - position.average_cost) * position.quantity
        return decimal_to_string(pnl_sum)

    def _resolve_position_metric(self, position: Position, portfolio: Portfolio, field: str) -> str:
        quotes = self._get_quotes_for_portfolio(portfolio)
        quote = quotes.get(position.symbol)
        if quote is None:
            return ""

        if field == "market_value":
            value = position.quantity * quote.price
            return decimal_to_string(value)

        if field == "unrealized_pnl":
            pnl = (quote.price - position.average_cost) * position.quantity
            return decimal_to_string(pnl)

        if field == "unrealized_pnl_percent":
            cost_basis = position.average_cost * position.quantity
            if cost_basis == 0:
                return ""
            pnl = (quote.price - position.average_cost) * position.quantity
            pct = pnl / cost_basis
            return decimal_to_string(pct)

        return ""
