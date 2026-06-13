from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from sqlalchemy.orm import Session

from app.core.formatting import to_utc
from app.schemas.memory import (
    MemoryLifecycleStatus,
    MemoryPromptSnippet,
    MemoryQuery,
    MemorySubjectRef,
)
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
        query: str | None = None,
        subject_refs: list[MemorySubjectRef] | None = None,
        kind: str | None = None,
        agent_key: str | None = None,
        max_items: int = _DEFAULT_MAX_ITEMS,
        max_characters: int = _DEFAULT_MAX_CHARACTERS,
        current_context: MemoryLookupContext | None = None,
    ) -> list[MemoryPromptSnippet]:
        if max_items <= 0 or max_characters <= 0:
            return []

        normalized_query = self._normalize_optional_text(query)
        normalized_kind = self._normalize_optional_text(kind)
        normalized_agent_key = self._normalize_optional_text(agent_key)
        snippets = self._ordered_snippets(
            query=normalized_query,
            subject_refs=subject_refs or [],
            kind=normalized_kind,
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
        query: str | None = None,
        subject_refs: list[MemorySubjectRef] | None = None,
        kind: str | None = None,
        agent_key: str | None = None,
        max_items: int = _DEFAULT_MAX_ITEMS,
        max_characters: int = _DEFAULT_MAX_CHARACTERS,
        current_context: MemoryLookupContext | None = None,
    ) -> str:
        snippets = self.get_prompt_snippets(
            query=query,
            subject_refs=subject_refs,
            kind=kind,
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
                query=query,
                subject_refs=subject_refs or [],
                kind=kind,
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
        query: str | None,
        subject_refs: list[MemorySubjectRef],
        kind: str | None,
        agent_key: str | None,
        current_context: MemoryLookupContext | None,
    ) -> list[MemoryPromptSnippet]:
        seen_memory_ids: set[str] = set()
        ordered: list[MemoryPromptSnippet] = []
        for group in self._query_groups(
            query=query,
            subject_refs=subject_refs,
            kind=kind,
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
        query: str | None,
        subject_refs: list[MemorySubjectRef],
        kind: str | None,
        agent_key: str | None,
    ) -> list[MemoryQuery]:
        groups = [
            MemoryQuery(
                query=query,
                subject_refs=subject_refs,
                kind=kind,
                agent_key=agent_key,
                status=MemoryLifecycleStatus.APPROVED,
            )
        ]
        if query is not None or subject_refs or kind is not None:
            groups.append(MemoryQuery(agent_key=agent_key, status=MemoryLifecycleStatus.APPROVED))
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
        return to_utc(snippet.outcome.observed_at)

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
        query: str | None,
        subject_refs: list[MemorySubjectRef],
        kind: str | None,
        agent_key: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            key: value
            for key, value in {
                "query": MemoryContextService._normalize_optional_text(query),
                "kind": MemoryContextService._normalize_optional_text(kind),
                "agentKey": MemoryContextService._normalize_optional_text(agent_key),
            }.items()
            if value is not None
        }
        if subject_refs:
            payload["subjectRefs"] = [
                subject_ref.model_dump(mode="json", by_alias=True, exclude_none=True)
                for subject_ref in subject_refs
            ]
        return payload

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


__all__ = ["MemoryContextService", "MemoryPromptSnippet"]
