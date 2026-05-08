from __future__ import annotations

from typing import Protocol

from app.schemas.memory import (
    MemoryArtifactRead,
    MemoryAuditLinks,
    MemoryEntryRead,
    MemoryOutcome,
    MemoryPromptSnippet,
    MemoryQuery,
    MemoryReflection,
    MemoryWriteRequest,
    MemoryWriteResult,
)


class MemoryStore(Protocol):
    def create_pending(self, payload: MemoryWriteRequest) -> MemoryWriteResult:
        """Stage a pending memory write and return the memory-domain result."""
        ...

    def get(self, memory_id: str) -> MemoryEntryRead:
        """Return a memory entry by opaque memory id."""
        ...

    def query(self, query: MemoryQuery) -> list[MemoryPromptSnippet]:
        """Return bounded model-visible memory snippets."""
        ...

    def resolve(self, memory_id: str, outcome: MemoryOutcome) -> MemoryEntryRead:
        """Stage a lifecycle resolution for an existing memory."""
        ...

    def append_reflection(self, memory_id: str, reflection: MemoryReflection) -> MemoryEntryRead:
        """Stage a reflection append for an existing resolved memory."""
        ...

    def list_artifacts_for_run(self, run_id: int) -> list[MemoryArtifactRead]:
        """Return UI/API-visible memory artifacts for a run."""
        ...

    def audit_links(self, memory_id: str) -> MemoryAuditLinks:
        """Return audit-only backing report links for projection paths."""
        ...


__all__ = ["MemoryStore"]
