from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from typing import cast as type_cast

from sqlalchemy import bindparam, case, cast, desc, func, inspect, literal, literal_column, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.agent_memory import (
    AgentMemoryChunk,
    AgentMemoryEmbedding,
    AgentMemoryEntry,
    AgentMemoryRevision,
    PgVector,
    RunMemoryEvent,
)
from app.repositories.base import BaseRepository

_ARTIFACT_EVENT_TYPES = ("written", "reused", "superseded", "reviewed")


@dataclass(frozen=True, slots=True)
class AgentMemoryLookupCandidate:
    entry: AgentMemoryEntry
    revision: AgentMemoryRevision
    lexical_score: float | None = None
    vector_distance: float | None = None
    vector_similarity: float | None = None


class AgentMemoryEntryRepository(BaseRepository[AgentMemoryEntry]):
    model = AgentMemoryEntry

    def get_by_memory_id(self, memory_id: str) -> AgentMemoryEntry | None:
        statement = select(self.model).where(self.model.memory_id == memory_id)
        return self._get_by_statement(statement)

    def get_by_memory_id_for_update(
        self,
        memory_id: str,
        *,
        nowait: bool = False,
    ) -> AgentMemoryEntry | None:
        statement = (
            select(self.model)
            .where(self.model.memory_id == memory_id)
            .with_for_update(nowait=nowait)
            .execution_options(populate_existing=True)
        )
        return self._get_by_statement(statement)

    def get_by_idempotency_key(self, idempotency_key: str) -> AgentMemoryEntry | None:
        statement = select(self.model).where(self.model.idempotency_key == idempotency_key)
        return self._get_by_statement(statement)

    def get_by_fallback_identity(
        self,
        *,
        scope_type: str,
        scope_key: str,
        kind: str,
        content_hash: str,
        source_run_id: int,
        source_agent_key: str,
        source_step_id: str | None,
        source_slot: str | None,
    ) -> AgentMemoryEntry | None:
        statement = select(self.model).where(
            self.model.idempotency_key.is_(None),
            self.model.scope_type == scope_type,
            self.model.scope_key == scope_key,
            self.model.kind == kind,
            self.model.content_hash == content_hash,
            self.model.source_run_id == source_run_id,
            self.model.source_agent_key == source_agent_key,
            (
                self.model.source_step_id.is_(source_step_id)
                if source_step_id is None
                else self.model.source_step_id == source_step_id
            ),
            (
                self.model.source_slot.is_(source_slot)
                if source_slot is None
                else self.model.source_slot == source_slot
            ),
        )
        return self._get_by_statement(statement)

    def list_by_memory_ids(self, memory_ids: Sequence[str]) -> list[AgentMemoryEntry]:
        if not memory_ids:
            return []
        statement = select(self.model).where(self.model.memory_id.in_(list(memory_ids)))
        return self._list(statement)

    def list_latest_for_lookup(
        self,
        *,
        query_text: str | None,
        scope_type: str | None,
        scope_key: str | None,
        subject_refs: Sequence[dict[str, str]],
        kind: str | None,
        status: str,
        agent_key: str | None,
        workflow_key: str | None,
        tags: Sequence[str],
        limit: int,
        offset: int,
    ) -> list[tuple[AgentMemoryEntry, AgentMemoryRevision]]:
        candidates = self.list_lexical_lookup_candidates(
            query_text=query_text,
            scope_type=scope_type,
            scope_key=scope_key,
            subject_refs=subject_refs,
            kind=kind,
            status=status,
            agent_key=agent_key,
            workflow_key=workflow_key,
            tags=tags,
            limit=limit,
            offset=offset,
        )
        return [(candidate.entry, candidate.revision) for candidate in candidates]

    def list_lexical_lookup_candidates(
        self,
        *,
        query_text: str | None,
        scope_type: str | None,
        scope_key: str | None,
        subject_refs: Sequence[dict[str, str]],
        kind: str | None,
        status: str,
        agent_key: str | None,
        workflow_key: str | None,
        tags: Sequence[str],
        limit: int,
        offset: int = 0,
    ) -> list[AgentMemoryLookupCandidate]:
        latest_versions = self._latest_revision_versions().subquery()
        statement = self._latest_revision_statement(latest_versions)
        filters = self._lookup_filters(
            scope_type=scope_type,
            scope_key=scope_key,
            subject_refs=subject_refs,
            kind=kind,
            status=status,
            agent_key=agent_key,
            workflow_key=workflow_key,
            tags=tags,
        )

        rank_expression: Any = literal(0.0)
        if query_text is not None:
            search_config: Any = literal_column("'simple'::regconfig")
            search_document = (
                AgentMemoryRevision.summary + literal_column("' '") + AgentMemoryRevision.content
            )
            search_vector = func.to_tsvector(search_config, search_document)
            search_query = func.plainto_tsquery(search_config, query_text)
            filters.append(search_vector.op("@@")(search_query))
            rank_expression = func.ts_rank_cd(search_vector, search_query)

        statement = (
            statement.add_columns(rank_expression.label("lexical_score"))
            .where(*filters)
            .order_by(
                desc(self._scope_specificity_expression()),
                desc(rank_expression),
                AgentMemoryRevision.created_at.desc(),
                self.model.memory_id.asc(),
            )
        )
        if offset > 0:
            statement = statement.offset(offset)
        statement = statement.limit(limit)

        rows = self.session.execute(statement).all()
        return [
            AgentMemoryLookupCandidate(
                entry=type_cast(AgentMemoryEntry, row[0]),
                revision=type_cast(AgentMemoryRevision, row[1]),
                lexical_score=self._float_or_none(row[2]),
            )
            for row in rows
        ]

    def list_vector_lookup_candidates(
        self,
        *,
        query_embedding: Sequence[float] | None,
        query_embedding_provider: str | None,
        query_embedding_model: str | None,
        scope_type: str | None,
        scope_key: str | None,
        subject_refs: Sequence[dict[str, str]],
        kind: str | None,
        status: str,
        agent_key: str | None,
        workflow_key: str | None,
        tags: Sequence[str],
        limit: int,
    ) -> list[AgentMemoryLookupCandidate]:
        if not query_embedding or not self._embedding_table_available():
            return []

        latest_versions = self._latest_revision_versions().subquery()
        query_vector = cast(
            bindparam("query_embedding", self._vector_literal(query_embedding)),
            PgVector(len(query_embedding)),
        )
        distance_expression: Any = AgentMemoryEmbedding.embedding.op("<=>")(query_vector)
        filters = self._lookup_filters(
            scope_type=scope_type,
            scope_key=scope_key,
            subject_refs=subject_refs,
            kind=kind,
            status=status,
            agent_key=agent_key,
            workflow_key=workflow_key,
            tags=tags,
        )
        filters.extend(
            [
                AgentMemoryEmbedding.status == "ready",
                AgentMemoryEmbedding.embedding.is_not(None),
                AgentMemoryEmbedding.embedding_dimensions == len(query_embedding),
                AgentMemoryEmbedding.content_hash == AgentMemoryChunk.content_hash,
                AgentMemoryChunk.source_content_hash == AgentMemoryRevision.content_hash,
            ]
        )
        if query_embedding_provider is not None:
            filters.append(AgentMemoryEmbedding.embedding_provider == query_embedding_provider)
        if query_embedding_model is not None:
            filters.append(AgentMemoryEmbedding.embedding_model == query_embedding_model)

        ranked_vectors = (
            select(
                self.model.id.label("entry_id"),
                AgentMemoryRevision.id.label("revision_row_id"),
                func.min(distance_expression).label("vector_distance"),
            )
            .select_from(self.model)
            .join(latest_versions, latest_versions.c.memory_entry_id == self.model.id)
            .join(
                AgentMemoryRevision,
                (AgentMemoryRevision.memory_entry_id == self.model.id)
                & (AgentMemoryRevision.version == latest_versions.c.version),
            )
            .join(
                AgentMemoryChunk,
                (AgentMemoryChunk.memory_entry_id == self.model.id)
                & (AgentMemoryChunk.memory_revision_id == AgentMemoryRevision.id),
            )
            .join(
                AgentMemoryEmbedding,
                (AgentMemoryEmbedding.memory_chunk_id == AgentMemoryChunk.id)
                & (AgentMemoryEmbedding.memory_entry_id == self.model.id)
                & (AgentMemoryEmbedding.memory_revision_id == AgentMemoryRevision.id),
            )
            .where(*filters)
            .group_by(self.model.id, AgentMemoryRevision.id)
            .subquery()
        )
        statement = (
            select(self.model, AgentMemoryRevision, ranked_vectors.c.vector_distance)
            .join(ranked_vectors, ranked_vectors.c.entry_id == self.model.id)
            .join(AgentMemoryRevision, AgentMemoryRevision.id == ranked_vectors.c.revision_row_id)
            .order_by(
                ranked_vectors.c.vector_distance.asc(),
                desc(self._scope_specificity_expression()),
                AgentMemoryRevision.created_at.desc(),
                self.model.memory_id.asc(),
            )
            .limit(limit)
        )
        rows = self.session.execute(statement).all()
        return [
            AgentMemoryLookupCandidate(
                entry=type_cast(AgentMemoryEntry, row[0]),
                revision=type_cast(AgentMemoryRevision, row[1]),
                vector_distance=self._float_or_none(row[2]),
                vector_similarity=self._vector_similarity(self._float_or_none(row[2])),
            )
            for row in rows
        ]

    @staticmethod
    def _latest_revision_versions() -> Any:
        return select(
            AgentMemoryRevision.memory_entry_id.label("memory_entry_id"),
            func.max(AgentMemoryRevision.version).label("version"),
        ).group_by(AgentMemoryRevision.memory_entry_id)

    def _latest_revision_statement(self, latest_versions: Any) -> Any:
        return (
            select(self.model, AgentMemoryRevision)
            .join(latest_versions, latest_versions.c.memory_entry_id == self.model.id)
            .join(
                AgentMemoryRevision,
                (AgentMemoryRevision.memory_entry_id == self.model.id)
                & (AgentMemoryRevision.version == latest_versions.c.version),
            )
        )

    def _lookup_filters(
        self,
        *,
        scope_type: str | None,
        scope_key: str | None,
        subject_refs: Sequence[dict[str, str]],
        kind: str | None,
        status: str,
        agent_key: str | None,
        workflow_key: str | None,
        tags: Sequence[str],
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [self.model.status == status]
        if scope_type is not None and scope_key is not None:
            filters.append(self.model.scope_type == scope_type)
            filters.append(self.model.scope_key == scope_key)
        if kind is not None:
            filters.append(self.model.kind == kind)
        if agent_key is not None:
            filters.append(self.model.source_agent_key == agent_key)
        if workflow_key is not None:
            filters.append(self.model.source_workflow_key == workflow_key)
        for subject_ref in subject_refs:
            filters.append(self.model.subject_refs.contains([subject_ref]))
        for tag in tags:
            filters.append(self.model.attributes.contains({"tags": [tag]}))
        return filters

    def _embedding_table_available(self) -> bool:
        bind = self.session.get_bind()
        return inspect(bind).has_table(AgentMemoryEmbedding.__tablename__)

    @staticmethod
    def _vector_literal(values: Sequence[float]) -> str:
        return "[" + ",".join(format(float(value), ".12g") for value in values) + "]"

    @staticmethod
    def _float_or_none(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float, str, Decimal)):
            return float(value)
        return float(str(value))

    @staticmethod
    def _vector_similarity(distance: float | None) -> float | None:
        if distance is None:
            return None
        return 1.0 / (1.0 + max(distance, 0.0))

    @classmethod
    def _scope_specificity_expression(cls) -> Any:
        return case(
            *(
                (cls.model.scope_type == scope_type, rank)
                for scope_type, rank in {
                    "agent": 5,
                    "run": 4,
                    "workflow": 3,
                    "package": 2,
                    "workspace": 1,
                }.items()
            ),
            else_=0,
        )


class AgentMemoryRevisionRepository(BaseRepository[AgentMemoryRevision]):
    model = AgentMemoryRevision

    def get_by_revision_id(self, revision_id: str) -> AgentMemoryRevision | None:
        statement = select(self.model).where(self.model.revision_id == revision_id)
        return self._get_by_statement(statement)

    def get_latest_for_entry(self, memory_entry_id: int) -> AgentMemoryRevision | None:
        statement = (
            select(self.model)
            .where(self.model.memory_entry_id == memory_entry_id)
            .order_by(self.model.version.desc(), self.model.id.desc())
            .limit(1)
        )
        return self._get_by_statement(statement)

    def list_latest_for_entry_ids(
        self,
        memory_entry_ids: Sequence[int],
    ) -> list[AgentMemoryRevision]:
        if not memory_entry_ids:
            return []
        latest_versions = (
            select(
                self.model.memory_entry_id.label("memory_entry_id"),
                func.max(self.model.version).label("version"),
            )
            .where(self.model.memory_entry_id.in_(list(memory_entry_ids)))
            .group_by(self.model.memory_entry_id)
            .subquery()
        )
        statement = select(self.model).join(
            latest_versions,
            (latest_versions.c.memory_entry_id == self.model.memory_entry_id)
            & (latest_versions.c.version == self.model.version),
        )
        return self._list(statement)


class RunMemoryEventRepository(BaseRepository[RunMemoryEvent]):
    model = RunMemoryEvent

    def list_for_run(self, run_id: int) -> list[RunMemoryEvent]:
        statement = (
            select(self.model)
            .where(self.model.run_id == run_id)
            .order_by(self.model.created_at.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def list_artifact_events_for_run(self, run_id: int) -> list[RunMemoryEvent]:
        statement = (
            select(self.model)
            .where(
                self.model.run_id == run_id,
                self.model.event_type.in_(_ARTIFACT_EVENT_TYPES),
                self.model.memory_id.is_not(None),
            )
            .order_by(self.model.created_at.asc(), self.model.id.asc())
        )
        return self._list(statement)

    def add_event(self, **fields: object) -> RunMemoryEvent:
        event = self.model(**fields)
        return self.add(event)


__all__ = [
    "AgentMemoryLookupCandidate",
    "AgentMemoryEntryRepository",
    "AgentMemoryRevisionRepository",
    "RunMemoryEventRepository",
]
