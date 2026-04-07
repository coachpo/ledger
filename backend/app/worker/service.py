from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import httpx

from app.core.formatting import normalize_symbol, parse_decimal_string
from app.schemas.backtest import TradeDecision
from app.schemas.backtest_callback import (
    CycleReportUpload,
    CycleReportUploadResponse,
    CycleTradesRequest,
)
from app.worker.schemas import (
    BacktestWebhookDispatch,
    BacktestWebhookDispatchAcceptedResponse,
    BacktestWebhookDispatchResponse,
)
from app.worker.trading_agents_adapter import TradingAgentsAdapter, TradingAgentsAnalysis

_FIXED_BUY_QUANTITY = 1
_POSITION_LINE_RE = re.compile(r"^-\s*(?P<symbol>[^:]+):\s*(?P<quantity>[^\s]+)\s+shares\s+@\s+.+$")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HeldPosition:
    symbol: str
    quantity_text: str
    quantity: Decimal


class BacktestWebhookWorkerService:
    def __init__(
        self,
        *,
        http_client_factory: Callable[[], httpx.Client],
        adapter_factory: Callable[[], TradingAgentsAdapter],
    ) -> None:
        self.http_client_factory = http_client_factory
        self.adapter_factory = adapter_factory

    def dispatch_async(
        self, payload: BacktestWebhookDispatch
    ) -> BacktestWebhookDispatchAcceptedResponse:
        thread = threading.Thread(target=self._run_dispatch, args=(payload,), daemon=True)
        thread.start()
        return BacktestWebhookDispatchAcceptedResponse(
            status="accepted",
            backtest_id=payload.backtest_id,
            cycle_date=payload.cycle_date,
        )

    def handle_dispatch(self, payload: BacktestWebhookDispatch) -> BacktestWebhookDispatchResponse:
        with closing(self.http_client_factory()) as http_client:
            adapter = self.adapter_factory()
            prompt_report = self._download_prompt_report(http_client, payload.report_download_url)
            positions = self._extract_positions(prompt_report)
            analyses = self._analyze_positions(payload, prompt_report, positions, adapter=adapter)
            report_content = self._render_analysis_report(payload, analyses)
            report_slug = self._upload_analysis_report(http_client, payload, report_content)
            decisions = self._build_trade_decisions(analyses)
            self._send_trade_callback(http_client, payload, decisions, report_slug)
            self._send_complete_callback(http_client, payload)

        return BacktestWebhookDispatchResponse(
            status="completed",
            report_slug=report_slug,
            decision_count=len(decisions),
            symbols=[analysis.position.symbol for analysis in analyses],
        )

    def _run_dispatch(self, payload: BacktestWebhookDispatch) -> None:
        try:
            self.handle_dispatch(payload)
        except Exception:
            logger.exception(
                "TradingAgents worker failed for backtest %s cycle %s",
                payload.backtest_id,
                payload.cycle_date.isoformat(),
            )

    def _download_prompt_report(self, http_client: httpx.Client, report_download_url: str) -> str:
        response = http_client.get(report_download_url)
        response.raise_for_status()
        return response.text

    def _extract_positions(self, prompt_report: str) -> list[HeldPosition]:
        positions: list[HeldPosition] = []
        in_positions = False

        for raw_line in prompt_report.splitlines():
            line = raw_line.strip()
            if line == "Positions:":
                in_positions = True
                continue

            if not in_positions:
                continue

            if not line:
                continue

            if line == "- None":
                return []

            match = _POSITION_LINE_RE.match(line)
            if match is None:
                if line.startswith("-"):
                    continue
                break

            quantity_text = match.group("quantity")
            positions.append(
                HeldPosition(
                    symbol=normalize_symbol(match.group("symbol")),
                    quantity_text=self._normalize_quantity_text(quantity_text),
                    quantity=parse_decimal_string(quantity_text),
                )
            )

        return positions

    def _analyze_positions(
        self,
        payload: BacktestWebhookDispatch,
        prompt_report: str,
        positions: list[HeldPosition],
        *,
        adapter: TradingAgentsAdapter,
    ) -> list[SymbolAnalysis]:
        analyses: list[SymbolAnalysis] = []

        for position in positions:
            raw_analysis = adapter.analyze_symbol(
                symbol=position.symbol,
                cycle_date=payload.cycle_date,
                prompt_report=prompt_report,
                position_quantity=position.quantity_text,
            )
            analyses.append(
                SymbolAnalysis(
                    position=position,
                    analysis=self._coerce_analysis(raw_analysis),
                )
            )

        return analyses

    def _render_analysis_report(
        self,
        payload: BacktestWebhookDispatch,
        analyses: list[SymbolAnalysis],
    ) -> str:
        lines = [
            "# TradingAgents Analysis",
            "",
            f"- Backtest ID: {payload.backtest_id}",
            f"- Cycle date: {payload.cycle_date.isoformat()}",
            f"- Prompt report slug: {payload.report_slug}",
            "",
        ]

        if not analyses:
            lines.append("No held symbols were found in the prompt report.")
            return "\n".join(lines)

        for index, symbol_analysis in enumerate(analyses):
            if index:
                lines.append("")
            lines.extend(
                [
                    f"## {symbol_analysis.position.symbol}",
                    f"- Label: {symbol_analysis.analysis.label}",
                    f"- Held quantity: {symbol_analysis.position.quantity_text}",
                    f"- Summary: {symbol_analysis.analysis.summary}",
                ]
            )

        return "\n".join(lines)

    def _upload_analysis_report(
        self, http_client: httpx.Client, payload: BacktestWebhookDispatch, content: str
    ) -> str:
        report_name = (
            f"tradingagents_backtest_{payload.backtest_id}_{payload.cycle_date.strftime('%Y%m%d')}"
        )
        request = CycleReportUpload(
            name=report_name,
            content=content,
            tags=["tradingagents", "phase1"],
        )
        response = http_client.post(
            f"{payload.callback_base_url}/report",
            json=request.model_dump(by_alias=True),
        )
        response.raise_for_status()
        report = CycleReportUploadResponse.model_validate(response.json())
        return report.slug

    def _build_trade_decisions(self, analyses: list[SymbolAnalysis]) -> list[TradeDecision]:
        decisions: list[TradeDecision] = []

        for symbol_analysis in analyses:
            action, quantity, note = self._translate_action(symbol_analysis)
            reasoning = f"{symbol_analysis.analysis.label}: {symbol_analysis.analysis.summary}"
            if note is not None:
                reasoning = f"{reasoning} {note}"
            decisions.append(
                TradeDecision(
                    symbol=symbol_analysis.position.symbol,
                    action=action,
                    quantity=quantity,
                    target_price=None,
                    reasoning=reasoning,
                )
            )

        return decisions

    def _translate_action(
        self, symbol_analysis: SymbolAnalysis
    ) -> tuple[Literal["BUY", "SELL", "HOLD"], int | None, str | None]:
        label = symbol_analysis.analysis.label.strip().upper()
        if label in {"BUY", "OVERWEIGHT"}:
            return "BUY", _FIXED_BUY_QUANTITY, None
        if label in {"SELL", "UNDERWEIGHT"}:
            if (
                symbol_analysis.position.quantity
                != symbol_analysis.position.quantity.to_integral_value()
            ):
                return (
                    "HOLD",
                    None,
                    (
                        f"Fractional held quantity {symbol_analysis.position.quantity_text} is not "
                        "supported for SELL in phase 1."
                    ),
                )
            return "SELL", int(symbol_analysis.position.quantity), None
        return "HOLD", None, None

    def _coerce_analysis(self, raw_analysis: Any) -> TradingAgentsAnalysis:
        if isinstance(raw_analysis, TradingAgentsAnalysis):
            return raw_analysis
        if isinstance(raw_analysis, dict):
            return TradingAgentsAnalysis(
                label=str(raw_analysis.get("label", "HOLD")).strip().upper(),
                summary=str(raw_analysis.get("summary", "HOLD")).strip(),
            )
        raise TypeError("TradingAgents adapter must return TradingAgentsAnalysis or a dict")

    def _send_trade_callback(
        self,
        http_client: httpx.Client,
        payload: BacktestWebhookDispatch,
        decisions: list[TradeDecision],
        report_slug: str,
    ) -> None:
        request = CycleTradesRequest(decisions=decisions, report_slug=report_slug)
        response = http_client.post(
            f"{payload.callback_base_url}/trades",
            json=request.model_dump(by_alias=True),
        )
        response.raise_for_status()

    def _send_complete_callback(
        self, http_client: httpx.Client, payload: BacktestWebhookDispatch
    ) -> None:
        response = http_client.post(f"{payload.callback_base_url}/complete")
        response.raise_for_status()

    def _normalize_quantity_text(self, quantity_text: str) -> str:
        quantity = parse_decimal_string(quantity_text)
        normalized = format(quantity.normalize(), "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        return normalized or "0"


@dataclass(frozen=True)
class SymbolAnalysis:
    position: HeldPosition
    analysis: TradingAgentsAnalysis
