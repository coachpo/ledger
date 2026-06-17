from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.workflow_memory import WorkflowMemoryProposal
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.schemas.workflow_memory import (
    DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
    WorkflowMemoryProposalCandidate,
    WorkflowMemoryScope,
)
from app.services.workflow_memory_detection import detect_workflow_memory_policy_hits

_SUPPORTED_KINDS = {"fact", "observation", "preference", "decision", "artifact"}


def _canonicalize_proposal_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if isinstance(value, list):
        return [_canonicalize_proposal_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: canonicalized
            for key, raw_value in sorted(value.items())
            if (canonicalized := _canonicalize_proposal_value(raw_value)) is not None
        }
    return value


def workflow_memory_content_fingerprint(
    *,
    kind: str,
    namespace: str,
    content: dict[str, Any],
) -> str:
    payload = {
        "kind": kind.strip().lower(),
        "namespace": namespace.strip().lower(),
        "content": _canonicalize_proposal_value(content),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def workflow_memory_proposal_idempotency_key(
    *,
    package_key: str,
    workflow_key: str,
    agent_key: str,
    step_id: str,
    run_id: int | None,
    invocation_id: str | None,
    source_output_path: str | None,
    namespace: str,
    kind: str,
    content_fingerprint: str,
) -> str:
    payload = [
        _canonicalize_proposal_value(package_key),
        _canonicalize_proposal_value(workflow_key),
        _canonicalize_proposal_value(agent_key),
        _canonicalize_proposal_value(step_id),
        run_id,
        _canonicalize_proposal_value(invocation_id),
        _canonicalize_proposal_value(source_output_path),
        namespace.strip().lower(),
        kind.strip().lower(),
        content_fingerprint,
    ]
    serialized = json.dumps(payload, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class WorkflowMemoryProposalStageResult:
    proposals: tuple[WorkflowMemoryProposal, ...]
    rejected_count: int = 0


class WorkflowMemoryProposalService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowMemoryRepository = WorkflowMemoryRepository(session)

    def stage_from_runtime_output(
        self,
        *,
        scope: WorkflowMemoryScope,
        runtime_output: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        run_id: int | None = None,
        invocation_id: str | None = None,
        source_output_path: str | None = None,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryProposalStageResult:
        candidates, rejected_count = self._extract_candidates(
            runtime_output=runtime_output,
            metadata=metadata or {},
            source_output_path=source_output_path,
        )
        result = self.stage_candidates(
            scope=scope,
            candidates=candidates,
            run_id=run_id,
            invocation_id=invocation_id,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        return WorkflowMemoryProposalStageResult(
            proposals=result.proposals,
            rejected_count=result.rejected_count + rejected_count,
        )

    def stage_candidates(
        self,
        *,
        scope: WorkflowMemoryScope,
        candidates: tuple[WorkflowMemoryProposalCandidate, ...],
        run_id: int | None = None,
        invocation_id: str | None = None,
        owner_type: str = DEFAULT_WORKFLOW_MEMORY_OWNER_TYPE,
        owner_id: str = DEFAULT_WORKFLOW_MEMORY_OWNER_ID,
    ) -> WorkflowMemoryProposalStageResult:
        staged: list[WorkflowMemoryProposal] = []
        rejected_count = 0
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_candidate(candidate, default_namespace=scope.namespace)
            if normalized is None:
                rejected_count += 1
                continue
            content_json = cast(dict[str, Any], normalized.content)
            content_fingerprint = workflow_memory_content_fingerprint(
                kind=normalized.kind,
                namespace=normalized.namespace or scope.namespace,
                content=content_json,
            )
            if content_fingerprint in seen:
                continue
            seen.add(content_fingerprint)
            idempotency_key = workflow_memory_proposal_idempotency_key(
                package_key=scope.package_key,
                workflow_key=scope.workflow_key,
                agent_key=scope.agent_key,
                step_id=scope.step_id,
                run_id=run_id,
                invocation_id=invocation_id,
                source_output_path=normalized.source_output_path,
                namespace=normalized.namespace or scope.namespace,
                kind=normalized.kind,
                content_fingerprint=content_fingerprint,
            )
            existing = self.repository.get_proposal_by_idempotency_key(
                idempotency_key,
                owner_type=owner_type,
                owner_id=owner_id,
            )
            if existing is not None:
                staged.append(existing)
                continue
            detectors_json = detect_workflow_memory_policy_hits(content_json)
            try:
                with self.session.begin_nested():
                    proposal = self.repository.create_proposal(
                        proposal_id=f"proposal_{uuid4().hex}",
                        owner_type=owner_type,
                        owner_id=owner_id,
                        run_id=run_id,
                        invocation_id=invocation_id,
                        package_key=scope.package_key,
                        workflow_key=scope.workflow_key,
                        agent_key=scope.agent_key,
                        step_id=scope.step_id,
                        namespace=normalized.namespace or scope.namespace,
                        kind=normalized.kind,
                        content_fingerprint=content_fingerprint,
                        idempotency_key=idempotency_key,
                        content_json=content_json,
                        reason=normalized.reason,
                        source_output_path=normalized.source_output_path,
                        detectors_json=detectors_json,
                        status="proposed",
                    )
                    self.session.flush()
            except IntegrityError:
                existing = self.repository.get_proposal_by_idempotency_key(
                    idempotency_key,
                    owner_type=owner_type,
                    owner_id=owner_id,
                )
                if existing is None:
                    raise
                proposal = existing
            staged.append(proposal)
        self.session.flush()
        return WorkflowMemoryProposalStageResult(tuple(staged), rejected_count)

    def _extract_candidates(
        self,
        *,
        runtime_output: dict[str, Any],
        metadata: dict[str, Any],
        source_output_path: str | None,
    ) -> tuple[tuple[WorkflowMemoryProposalCandidate, ...], int]:
        raw_candidates = [
            *self._raw_candidate_list(runtime_output.get("memoryProposals")),
            *self._raw_candidate_list(runtime_output.get("memory")),
            *self._raw_candidate_list(metadata.get("memoryProposals")),
        ]
        candidates: list[WorkflowMemoryProposalCandidate] = []
        rejected_count = 0
        for raw_candidate in raw_candidates:
            if not isinstance(raw_candidate, dict):
                rejected_count += 1
                continue
            candidate_data = dict(cast(dict[str, Any], raw_candidate))
            candidate_data.setdefault("sourceOutputPath", source_output_path)
            try:
                candidates.append(WorkflowMemoryProposalCandidate.model_validate(candidate_data))
            except ValueError:
                rejected_count += 1
        return tuple(candidates), rejected_count

    def _raw_candidate_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    def _normalize_candidate(
        self,
        candidate: WorkflowMemoryProposalCandidate,
        *,
        default_namespace: str,
    ) -> WorkflowMemoryProposalCandidate | None:
        kind = candidate.kind.strip().lower()
        namespace = (candidate.namespace or default_namespace).strip().lower()
        if kind not in _SUPPORTED_KINDS or not namespace:
            return None
        content = candidate.content
        if isinstance(content, str):
            normalized_text = _canonicalize_proposal_value(content)
            content_json: dict[str, Any] = {"text": normalized_text}
        else:
            content_json = _canonicalize_proposal_value(content)
        if not content_json or any(
            isinstance(value, str) and not value.strip() for value in content_json.values()
        ):
            return None
        return WorkflowMemoryProposalCandidate(
            kind=kind,
            namespace=namespace,
            content=content_json,
            reason=candidate.reason.strip() if candidate.reason else None,
            source_output_path=candidate.source_output_path,
        )


__all__ = [
    "WorkflowMemoryProposalService",
    "WorkflowMemoryProposalStageResult",
    "workflow_memory_content_fingerprint",
    "workflow_memory_proposal_idempotency_key",
]
