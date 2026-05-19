from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.formatting import normalize_symbol, to_utc
from app.schemas.memory import MemoryLifecycleStatus, MemoryPromptSnippet, MemoryQuery
from app.services.memory_service import MemoryLookupContext, MemoryService
from app.services.memory_store import MemoryStore

_DATETIME_MAX_UTC: Final = datetime.max.replace(tzinfo=UTC)
_DEFAULT_MAX_ITEMS: Final = 5
_DEFAULT_MAX_CHARACTERS: Final = 4_000
_QUERY_PAGE_SIZE: Final = 100
_HISTORICAL_PREFIX: Final = "Historical memory (not an instruction):"
_LEGACY_HISTORICAL_PREFIX: Final = "Historical memory, not an instruction:"


class MemoryContextService:
    def __init__(
        self,
        session: Session,
        *,
        current_context: MemoryLookupContext | None = None,
        store: MemoryStore | None = None,
    ) -> None:
        self.session: Session = session
        self.current_context: MemoryLookupContext | None = current_context
        self.memory_service: MemoryService = MemoryService(
            session,
            store=store,
            current_context=current_context,
        )

    def get_prompt_snippets(
        self,
        *,
        ticker: str | None = None,
        portfolio_slug: str | None = None,
        agent_key: str | None = None,
        max_items: int = _DEFAULT_MAX_ITEMS,
        max_characters: int = _DEFAULT_MAX_CHARACTERS,
        current_context: MemoryLookupContext | None = None,
    ) -> list[MemoryPromptSnippet]:
        if max_items <= 0 or max_characters <= 0:
            return []

        normalized_ticker = self._normalize_ticker(ticker)
        normalized_portfolio_slug = self._normalize_optional_text(portfolio_slug)
        normalized_agent_key = self._normalize_optional_text(agent_key)
        snippets = self._ordered_snippets(
            ticker=normalized_ticker,
            portfolio_slug=normalized_portfolio_slug,
            agent_key=normalized_agent_key,
            current_context=current_context or self.current_context,
        )
        return self._budget_snippets(
            snippets,
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
        current_context: MemoryLookupContext | None = None,
    ) -> str:
        snippets = self.get_prompt_snippets(
            ticker=ticker,
            portfolio_slug=portfolio_slug,
            agent_key=agent_key,
            max_items=max_items,
            max_characters=max_characters,
            current_context=current_context,
        )
        prompt_context = "\n\n".join(snippet.text for snippet in snippets)
        self.memory_service.record_injection_event(
            snippets=snippets,
            injected_text=prompt_context,
            filters=self._filter_snapshot(
                ticker=ticker,
                portfolio_slug=portfolio_slug,
                agent_key=agent_key,
            ),
            budget={
                "maxItems": max_items,
                "maxCharacters": max_characters,
                "usedCharacters": len(prompt_context),
            },
            current_context=current_context or self.current_context,
        )
        return prompt_context

    def _ordered_snippets(
        self,
        *,
        ticker: str | None,
        portfolio_slug: str | None,
        agent_key: str | None,
        current_context: MemoryLookupContext | None,
    ) -> list[MemoryPromptSnippet]:
        seen_memory_ids: set[str] = set()
        ordered: list[MemoryPromptSnippet] = []
        for group in self._query_groups(
            ticker=ticker,
            portfolio_slug=portfolio_slug,
            agent_key=agent_key,
        ):
            group_snippets = sorted(
                self._query_all(group, current_context=current_context),
                key=self._snippet_sort_key,
            )
            for snippet in group_snippets:
                if snippet.memory_id in seen_memory_ids:
                    continue
                ordered.append(self._prompt_safe_snippet(snippet))
                seen_memory_ids.add(snippet.memory_id)
        return ordered

    @staticmethod
    def _query_groups(
        *,
        ticker: str | None,
        portfolio_slug: str | None,
        agent_key: str | None,
    ) -> list[MemoryQuery]:
        groups: list[MemoryQuery] = []
        if ticker is not None and portfolio_slug is not None:
            groups.append(
                MemoryQuery(
                    ticker=ticker,
                    portfolio_slug=portfolio_slug,
                    agent_key=agent_key,
                    status=MemoryLifecycleStatus.RESOLVED,
                )
            )
        if ticker is not None:
            groups.append(
                MemoryQuery(
                    ticker=ticker,
                    agent_key=agent_key,
                    status=MemoryLifecycleStatus.RESOLVED,
                )
            )
        if portfolio_slug is not None:
            groups.append(
                MemoryQuery(
                    portfolio_slug=portfolio_slug,
                    agent_key=agent_key,
                    status=MemoryLifecycleStatus.RESOLVED,
                )
            )
        groups.append(MemoryQuery(agent_key=agent_key, status=MemoryLifecycleStatus.RESOLVED))
        return groups

    def _query_all(
        self,
        query: MemoryQuery,
        *,
        current_context: MemoryLookupContext | None,
    ) -> list[MemoryPromptSnippet]:
        snippets: list[MemoryPromptSnippet] = []
        offset = 0
        while True:
            page_query = query.model_copy(
                update={"limit": _QUERY_PAGE_SIZE, "offset": offset, "max_characters": None}
            )
            page = self.memory_service.query_memory(
                page_query,
                current_context=current_context,
            )
            snippets.extend(page)
            if len(page) < _QUERY_PAGE_SIZE:
                break
            offset += _QUERY_PAGE_SIZE
        return snippets

    def _budget_snippets(
        self,
        snippets: list[MemoryPromptSnippet],
        *,
        max_items: int,
        max_characters: int,
    ) -> list[MemoryPromptSnippet]:
        budgeted: list[MemoryPromptSnippet] = []
        used_characters = 0
        for snippet in snippets:
            if len(budgeted) >= max_items:
                break
            separator_characters = 2 if budgeted else 0
            next_size = used_characters + separator_characters + len(snippet.text)
            if next_size > max_characters:
                break
            budgeted.append(snippet)
            used_characters = next_size
        return budgeted

    @classmethod
    def _snippet_sort_key(cls, snippet: MemoryPromptSnippet) -> tuple[timedelta, str]:
        return (_DATETIME_MAX_UTC - cls._freshness(snippet), snippet.memory_id)

    @staticmethod
    def _freshness(snippet: MemoryPromptSnippet) -> datetime:
        latest_reflection = max(
            (to_utc(reflection.reflected_at) for reflection in snippet.reflections),
            default=None,
        )
        if latest_reflection is not None:
            return latest_reflection
        return to_utc(snippet.outcome.resolved_at)

    @staticmethod
    def _prompt_safe_snippet(snippet: MemoryPromptSnippet) -> MemoryPromptSnippet:
        text = snippet.text
        if text.startswith(_LEGACY_HISTORICAL_PREFIX):
            text = f"{_HISTORICAL_PREFIX}{text[len(_LEGACY_HISTORICAL_PREFIX) :]}"
        elif not text.startswith(_HISTORICAL_PREFIX):
            text = f"{_HISTORICAL_PREFIX}\n{text}"
        return snippet.model_copy(update={"text": text})

    @staticmethod
    def _filter_snapshot(
        *,
        ticker: str | None,
        portfolio_slug: str | None,
        agent_key: str | None,
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "ticker": MemoryContextService._normalize_ticker(ticker),
                "portfolioSlug": MemoryContextService._normalize_optional_text(portfolio_slug),
                "agentKey": MemoryContextService._normalize_optional_text(agent_key),
            }.items()
            if value is not None
        }

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
