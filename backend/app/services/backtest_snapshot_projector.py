from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import business_rule_error
from app.models.backtest_orchestration_snapshot import BacktestOrchestrationSnapshot
from app.models.runtime_run import RuntimeRun
from app.models.runtime_run_artifact import RuntimeRunArtifact
from app.repositories.runtime_approval import RuntimeApprovalRepository
from app.repositories.runtime_run import RuntimeRunRepository
from app.repositories.runtime_trace_event import RuntimeTraceEventRepository
from app.repositories.workflow_spec import WorkflowSpecRepository


class BacktestSnapshotProjector:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.run_repository = RuntimeRunRepository(session)
        self.trace_repository = RuntimeTraceEventRepository(session)
        self.approval_repository = RuntimeApprovalRepository(session)
        self.workflow_repository = WorkflowSpecRepository(session)

    def project_latest_attempt(self, run_id: int) -> bool:
        run = self.session.get(RuntimeRun, run_id)
        if run is None:
            raise business_rule_error(
                "runtime_run_not_found",
                f"Runtime run {run_id} was not found for snapshot projection",
            )
        if run.caller_type != "backtest" or run.caller_id is None or run.caller_scope_key is None:
            return False

        if not self._is_latest_attempt(run):
            return False

        artifact = self.session.get(RuntimeRunArtifact, run.id)
        if artifact is None:
            raise business_rule_error(
                "runtime_artifact_not_found",
                f"Runtime run {run.id} is missing its artifact for snapshot projection",
            )
        if run.workflow_spec_key is None or run.workflow_spec_version is None:
            raise business_rule_error(
                "runtime_backtest_workflow_not_configured",
                f"Backtest run {run.id} is missing its pinned workflow target",
            )
        workflow = self.workflow_repository.get_by_key_version(
            run.workflow_spec_key,
            run.workflow_spec_version,
        )
        if workflow is None:
            raise business_rule_error(
                "runtime_workflow_not_found",
                (
                    f"Workflow spec {run.workflow_spec_key!r} v{run.workflow_spec_version} "
                    "was not found for snapshot projection"
                ),
            )

        cycle_date = self._parse_cycle_date(run)
        snapshot = self.session.scalar(
            select(BacktestOrchestrationSnapshot).where(
                BacktestOrchestrationSnapshot.backtest_id == run.caller_id,
                BacktestOrchestrationSnapshot.cycle_date == cycle_date,
            )
        )
        if snapshot is None:
            snapshot = BacktestOrchestrationSnapshot(
                backtest_id=run.caller_id,
                cycle_date=cycle_date,
                prompt_report_slug="",
                orchestration_pattern_key=workflow.key,
                pattern_policy_version=self._pattern_policy_version(workflow.mention_policy),
                entry_prompt_hash=artifact.entry_prompt_hash,
                full_user_prompt_hash=artifact.full_user_prompt_hash,
                execution_mode=str(workflow.execution_mode or "structured_output"),
                resolved_mentions=[],
                mentioned_target_outputs=[],
                resolved_builtin_versions=[],
                resolved_role_versions=[],
                resolved_character_versions=[],
                resolved_bundle_versions=[],
                resolved_tool_versions=[],
                resolved_connector_versions=[],
                tool_call_trace=[],
                approval_trace="not_required",
            )
            self.session.add(snapshot)

        snapshot.prompt_report_slug = artifact.prompt_report_slug or ""
        snapshot.orchestration_pattern_key = workflow.key
        snapshot.pattern_policy_version = self._pattern_policy_version(workflow.mention_policy)
        snapshot.entry_prompt_hash = artifact.entry_prompt_hash
        snapshot.full_user_prompt_hash = artifact.full_user_prompt_hash
        snapshot.execution_mode = str(workflow.execution_mode or "structured_output")
        snapshot.resolved_mentions = self._project_resolved_mentions(artifact.resolved_mentions)
        snapshot.mentioned_target_outputs = self._copy_json_list(artifact.mentioned_target_outputs)
        snapshot.resolved_builtin_versions = self._copy_json_list(
            artifact.resolved_builtin_versions
        )
        snapshot.resolved_role_versions = self._copy_json_list(artifact.resolved_role_versions)
        snapshot.resolved_character_versions = self._copy_json_list(
            artifact.resolved_character_versions
        )
        snapshot.resolved_bundle_versions = self._copy_json_list(artifact.resolved_bundle_versions)
        snapshot.resolved_tool_versions = self._copy_json_list(artifact.resolved_tool_versions)
        snapshot.resolved_connector_versions = self._copy_json_list(
            artifact.resolved_connector_versions
        )
        snapshot.tool_call_trace = self._project_tool_call_trace(run.id)
        snapshot.approval_trace = self._project_approval_trace(run.id, artifact)

        if not self._is_latest_attempt(run):
            self.session.rollback()
            return False

        self.session.commit()
        self.session.refresh(snapshot)
        return True

    def _is_latest_attempt(self, run: RuntimeRun) -> bool:
        with self.session.no_autoflush:
            latest = self.run_repository.get_latest_attempt(
                caller_type=run.caller_type,
                caller_id=run.caller_id,
                caller_scope_key=run.caller_scope_key,
            )
        return latest is not None and latest.id == run.id

    @staticmethod
    def _parse_cycle_date(run: RuntimeRun) -> date:
        caller_scope_key = str(run.caller_scope_key or "").strip()
        if not caller_scope_key:
            raise business_rule_error(
                "runtime_backtest_cycle_date_invalid",
                f"Run {run.id} is missing its cycle date scope key",
            )
        try:
            return date.fromisoformat(caller_scope_key)
        except ValueError as exc:
            raise business_rule_error(
                "runtime_backtest_cycle_date_invalid",
                f"Run {run.id} has an invalid cycle date scope key {caller_scope_key!r}",
            ) from exc

    @staticmethod
    def _pattern_policy_version(mention_policy: object) -> int:
        if isinstance(mention_policy, dict):
            raw_version = mention_policy.get("version") or mention_policy.get("Version")
            if raw_version is not None:
                return int(raw_version)
        return 1

    @staticmethod
    def _copy_json_list(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @classmethod
    def _project_resolved_mentions(cls, value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        projected: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            projected.append(
                {
                    "original_text": cls._required_text(item, "originalText", "original_text"),
                    "handle": cls._required_text(item, "sourceHandle", "source_handle", "handle"),
                    "canonical_target_id": cls._required_text(
                        item,
                        "canonicalTargetId",
                        "canonical_target_id",
                    ),
                    "target_type": cls._required_text(item, "targetType", "target_type"),
                    "role_id": cls._optional_int(item, "legacyRoleId", "role_id"),
                    "role_version": cls._optional_int(
                        item,
                        "legacyRoleVersion",
                        "role_version",
                    ),
                    "character_id": cls._optional_int(
                        item,
                        "legacyCharacterId",
                        "character_id",
                    ),
                    "character_version": cls._optional_int(
                        item,
                        "legacyCharacterVersion",
                        "character_version",
                    ),
                    "mention_order": cls._required_int(item, "mentionOrder", "mention_order"),
                }
            )
        return projected

    def _project_tool_call_trace(self, run_id: int) -> list[dict[str, Any]]:
        trace_events = self.trace_repository.list_for_run(run_id)
        projected: list[dict[str, Any]] = []
        for event in trace_events:
            if event.event_type != "TOOL_CALLED" or not isinstance(event.payload, dict):
                continue
            projected.append(dict(event.payload))
        return projected

    def _project_approval_trace(
        self,
        run_id: int,
        artifact: RuntimeRunArtifact,
    ) -> list[dict[str, Any]] | str:
        approvals = self.approval_repository.list_for_run(run_id)
        if not approvals:
            return "not_required"

        approval_request_order = self._approval_request_order(run_id)
        approvals_sorted = sorted(
            approvals,
            key=lambda approval: (
                approval_request_order.get(approval.id, len(approval_request_order)),
                approval.created_at,
                approval.id,
            ),
        )
        capability_details = self._resolved_capability_details(artifact)
        projected: list[dict[str, Any]] = []
        for fallback_index, approval in enumerate(approvals_sorted):
            call_index = approval_request_order.get(approval.id, fallback_index)
            capability = capability_details.get(approval.capability_key)
            projected.append(
                {
                    "call_index": call_index,
                    "tool_id": approval.capability_key,
                    "status": approval.status.lower(),
                    "kind": capability.get("kind") if capability is not None else None,
                    "transport": capability.get("transport") if capability is not None else None,
                }
            )
        return projected

    def _approval_request_order(self, run_id: int) -> dict[int, int]:
        trace_events = self.trace_repository.list_for_run(run_id)
        order: dict[int, int] = {}
        next_index = 0
        for event in trace_events:
            if event.event_type != "APPROVAL_REQUESTED" or event.approval_id is None:
                continue
            order[event.approval_id] = next_index
            next_index += 1
        return order

    @staticmethod
    def _resolved_capability_details(
        artifact: RuntimeRunArtifact,
    ) -> dict[str, dict[str, str | None]]:
        details: dict[str, dict[str, str | None]] = {}
        if not isinstance(artifact.resolved_capabilities, list):
            return details
        for item in artifact.resolved_capabilities:
            if not isinstance(item, dict):
                continue
            capability_key = str(
                item.get("capabilityKey") or item.get("capability_key") or ""
            ).strip()
            if not capability_key:
                continue
            raw_kind = item.get("capabilityType")
            if raw_kind is None:
                raw_kind = item.get("capability_type")
            kind = str(raw_kind).strip() or None
            raw_transport = item.get("transport")
            transport = str(raw_transport).strip() if raw_transport is not None else None
            details[capability_key] = {"kind": kind, "transport": transport}
        return details

    @staticmethod
    def _required_text(item: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        raise business_rule_error(
            "runtime_snapshot_projection_invalid",
            f"Snapshot projection is missing required text fields {keys}",
        )

    @staticmethod
    def _optional_int(item: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            return int(value)
        return None

    @classmethod
    def _required_int(cls, item: dict[str, Any], *keys: str) -> int:
        value = cls._optional_int(item, *keys)
        if value is None:
            raise business_rule_error(
                "runtime_snapshot_projection_invalid",
                f"Snapshot projection is missing required integer fields {keys}",
            )
        return value
