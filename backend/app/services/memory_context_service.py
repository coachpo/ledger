from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Final

from sqlalchemy.orm import Session

from app.core.formatting import decimal_to_string, normalize_symbol, to_utc
from app.repositories.report import ReportRepository
from app.schemas.memory_report import (
    AGENT_MEMORY_REVIEW_TYPE,
    AGENT_MEMORY_VERSION_GROUP,
    AgentMemoryReportAnalysis,
    AgentMemoryReportMetadata,
)

_MEMORY_REPORT_SOURCE: Final = "external"
_DATETIME_MAX_UTC: Final = datetime.max.replace(tzinfo=UTC)
_DEFAULT_MAX_ITEMS: Final = 5
_DEFAULT_MAX_CHARACTERS: Final = 4_000


@dataclass(frozen=True, slots=True)
class MemoryPromptSnippet:
    report_id: int
    report_slug: str
    text: str


@dataclass(frozen=True, slots=True)
class _ResolvedMemoryCandidate:
    report_id: int
    report_slug: str
    created_at: datetime
    analysis: AgentMemoryReportAnalysis

    @property
    def freshness(self) -> datetime:
        latest_reflection = max(
            (to_utc(reflection.reflected_at) for reflection in self.analysis.reflections),
            default=None,
        )
        if latest_reflection is not None:
            return latest_reflection
        if self.analysis.resolved_at is not None:
            return to_utc(self.analysis.resolved_at)
        return to_utc(self.created_at)


class MemoryContextService:
    def __init__(self, session: Session) -> None:
        self.repository: ReportRepository = ReportRepository(session)

    def get_prompt_snippets(
        self,
        *,
        ticker: str | None = None,
        portfolio_slug: str | None = None,
        agent_key: str | None = None,
        max_items: int = _DEFAULT_MAX_ITEMS,
        max_characters: int = _DEFAULT_MAX_CHARACTERS,
    ) -> list[MemoryPromptSnippet]:
        if max_items <= 0 or max_characters <= 0:
            return []

        normalized_ticker = self._normalize_ticker(ticker)
        normalized_portfolio_slug = self._normalize_optional_text(portfolio_slug)
        normalized_agent_key = self._normalize_optional_text(agent_key)
        ordered_candidates = sorted(
            self._resolved_memory_candidates(),
            key=lambda candidate: self._sort_key(
                candidate,
                ticker=normalized_ticker,
                portfolio_slug=normalized_portfolio_slug,
                agent_key=normalized_agent_key,
            ),
        )
        return self._budget_snippets(
            ordered_candidates,
            max_items=max_items,
            max_characters=max_characters,
        )

    def build_prompt_context(
        self,
        *,
        ticker: str | None = None,
        portfolio_slug: str | None = None,
        agent_key: str | None = None,
        max_items: int = _DEFAULT_MAX_ITEMS,
        max_characters: int = _DEFAULT_MAX_CHARACTERS,
    ) -> str:
        snippets = self.get_prompt_snippets(
            ticker=ticker,
            portfolio_slug=portfolio_slug,
            agent_key=agent_key,
            max_items=max_items,
            max_characters=max_characters,
        )
        return "\n\n".join(snippet.text for snippet in snippets)

    def _resolved_memory_candidates(self) -> list[_ResolvedMemoryCandidate]:
        reports = self.repository.list_all(
            review_type=AGENT_MEMORY_REVIEW_TYPE,
            source=_MEMORY_REPORT_SOURCE,
        )
        candidates: list[_ResolvedMemoryCandidate] = []
        for report in reports:
            try:
                metadata = AgentMemoryReportMetadata.model_validate(report.metadata_)
            except ValueError:
                continue

            analysis = metadata.analysis
            if analysis.version_group != AGENT_MEMORY_VERSION_GROUP:
                continue
            if analysis.resolved_status != "resolved":
                continue
            candidates.append(
                _ResolvedMemoryCandidate(
                    report_id=report.id,
                    report_slug=report.slug,
                    created_at=report.created_at,
                    analysis=analysis,
                )
            )
        return candidates

    @classmethod
    def _sort_key(
        cls,
        candidate: _ResolvedMemoryCandidate,
        *,
        ticker: str | None,
        portfolio_slug: str | None,
        agent_key: str | None,
    ) -> tuple[int, int, int, timedelta, str, int]:
        analysis = candidate.analysis
        return (
            cls._mismatch(ticker, analysis.ticker),
            cls._mismatch(portfolio_slug, analysis.portfolio_slug),
            cls._mismatch(agent_key, analysis.agent_key),
            _DATETIME_MAX_UTC - candidate.freshness,
            candidate.report_slug,
            candidate.report_id,
        )

    @staticmethod
    def _mismatch(expected: str | None, actual: str | None) -> int:
        if expected is None:
            return 0
        return 0 if actual == expected else 1

    def _budget_snippets(
        self,
        candidates: list[_ResolvedMemoryCandidate],
        *,
        max_items: int,
        max_characters: int,
    ) -> list[MemoryPromptSnippet]:
        snippets: list[MemoryPromptSnippet] = []
        used_characters = 0
        for candidate in candidates:
            if len(snippets) >= max_items:
                break

            text = self._render_snippet(candidate)
            separator_characters = 2 if snippets else 0
            next_size = used_characters + separator_characters + len(text)
            if next_size > max_characters:
                break

            snippets.append(
                MemoryPromptSnippet(
                    report_id=candidate.report_id,
                    report_slug=candidate.report_slug,
                    text=text,
                )
            )
            used_characters = next_size
        return snippets

    @classmethod
    def _render_snippet(cls, candidate: _ResolvedMemoryCandidate) -> str:
        analysis = candidate.analysis
        lines = [
            f"### Memory {candidate.report_slug}",
            f"- Report ID: {candidate.report_id}",
            f"- Ticker: {analysis.ticker}",
            f"- Action: {analysis.decision.action}",
            f"- Agent: {analysis.agent_key}@{analysis.agent_version}",
        ]
        if analysis.portfolio_slug is not None:
            lines.append(f"- Portfolio: {analysis.portfolio_slug}")
        if analysis.decision_summary is not None:
            lines.append(f"- Decision summary: {analysis.decision_summary}")
        lines.append(f"- Outcome: {cls._render_outcome(analysis)}")
        if analysis.reflections:
            lines.append("- Reflections:")
            for reflection in analysis.reflections:
                reflected_at = cls._format_datetime(reflection.reflected_at)
                lines.append(f"  - {reflected_at}: {reflection.reflection}")
        return "\n".join(lines)

    @classmethod
    def _render_outcome(cls, analysis: AgentMemoryReportAnalysis) -> str:
        parts = [f"resolved at {cls._format_datetime(analysis.resolved_at)}"]
        if analysis.raw_return is not None:
            parts.append(f"raw return {cls._format_decimal(analysis.raw_return)}")
        if analysis.benchmark_return is not None:
            parts.append(f"benchmark return {cls._format_decimal(analysis.benchmark_return)}")
        if analysis.alpha is not None:
            parts.append(f"alpha {cls._format_decimal(analysis.alpha)}")
        return "; ".join(parts)

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        if value is None:
            return "unknown"
        return to_utc(value).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return decimal_to_string(value)

    @staticmethod
    def _normalize_ticker(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_symbol(value)
        return normalized or None

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


__all__ = ["MemoryContextService", "MemoryPromptSnippet"]
