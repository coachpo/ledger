# pyright: reportExplicitAny=false
from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, TypedDict, cast

from fastapi import status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.errors import ApiError, not_found_error, validation_error
from app.models.workflow_package import WorkflowPackage, WorkflowPackageRuntimeInputEntry
from app.repositories.workflow_package import WorkflowPackageRepository
from app.services.output_schema_compiler import OutputSchemaCompiler
from app.services.run_input_validation import validate_run_input_payload
from app.services.workflow_package_runtime_inputs import (
    RuntimeInputStaleEvaluation,
    RuntimeInputStoredMetadata,
    RuntimeInputWorkflowMetadata,
    build_runtime_input_current_metadata,
    evaluate_runtime_input_staleness,
    validate_runtime_input_payload_safety,
)

LOCAL_RUNTIME_INPUT_OWNER_TYPE: Final = "local_user"
LOCAL_RUNTIME_INPUT_OWNER_ID: Final = "default"
RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT: Final = 20
_RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE: Final = (
    "Workflow package runtime input entry validation failed"
)

WorkflowPackageRuntimeInputSlot = Literal["history", "personal"]


class _RuntimeInputScope(TypedDict):
    package_id: int
    workflow_key: str
    owner_type: str
    owner_id: str


class _RuntimeInputMetadataFields(TypedDict):
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema_snapshot: dict[str, object]


class _UnsetType:
    pass


_UNSET = _UnsetType()


@dataclass(frozen=True)
class WorkflowPackageRuntimeInputEntryRead:
    id: int
    package_id: int
    workflow_key: str
    slot: WorkflowPackageRuntimeInputSlot
    name: str | None
    payload: dict[str, Any]
    source_kind: str
    manifest_hash: str
    compiled_hash: str
    schema_fingerprint: str
    input_schema_snapshot: dict[str, Any] | None
    source_run_id: int | None
    stale: RuntimeInputStaleEvaluation
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkflowPackageRuntimeInputRegistryRead:
    package_id: int
    package_key: str
    workflow_key: str
    owner_type: str
    owner_id: str
    current_metadata: RuntimeInputWorkflowMetadata | None
    personal: list[WorkflowPackageRuntimeInputEntryRead]
    history: list[WorkflowPackageRuntimeInputEntryRead]


class WorkflowPackageRuntimeInputRegistryService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session
        self.repository: WorkflowPackageRepository = WorkflowPackageRepository(session)
        self.schema_compiler: OutputSchemaCompiler = OutputSchemaCompiler()

    def list_registry(
        self,
        package_id: int,
        workflow_key: str,
        *,
        owner_type: str = LOCAL_RUNTIME_INPUT_OWNER_TYPE,
        owner_id: str = LOCAL_RUNTIME_INPUT_OWNER_ID,
    ) -> WorkflowPackageRuntimeInputRegistryRead:
        package = self._get_package(package_id)
        scope = self._scope(
            package_id=package.id,
            workflow_key=workflow_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        current_metadata = self._current_metadata(package, scope["workflow_key"])
        personal = self.repository.list_runtime_input_personal_entries(**scope)
        history = self.repository.list_runtime_input_history_entries(**scope)
        return WorkflowPackageRuntimeInputRegistryRead(
            package_id=package.id,
            package_key=package.key,
            workflow_key=scope["workflow_key"],
            owner_type=scope["owner_type"],
            owner_id=scope["owner_id"],
            current_metadata=current_metadata,
            personal=[self._to_entry_read(entry, current_metadata) for entry in personal],
            history=[self._to_entry_read(entry, current_metadata) for entry in history],
        )

    def create_personal_entry(
        self,
        package_id: int,
        workflow_key: str,
        *,
        payload: object,
        name: str | None = None,
        source_kind: str = "manual",
        owner_type: str = LOCAL_RUNTIME_INPUT_OWNER_TYPE,
        owner_id: str = LOCAL_RUNTIME_INPUT_OWNER_ID,
        source_run_id: int | None = None,
    ) -> WorkflowPackageRuntimeInputEntryRead:
        package = self._get_package(package_id)
        scope = self._scope(
            package_id=package.id,
            workflow_key=workflow_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        current_metadata = self._require_current_metadata(package, scope["workflow_key"])
        safe_payload = validate_runtime_input_payload_safety(payload)
        canonical_payload = self._canonical_personal_payload(current_metadata, safe_payload)
        try:
            self._acquire_scope_lock(scope, slot="personal")
            self._enforce_personal_limit(scope)
            entry = self.repository.create_runtime_input_personal_entry(
                **scope,
                name=self._normalize_name(name),
                payload=deepcopy(canonical_payload),
                source_kind=self._normalize_source_kind(source_kind),
                source_run_id=self._normalize_source_run_id(source_run_id),
                **self._metadata_fields(current_metadata),
            )
            self.session.commit()
            self.session.refresh(entry)
        except Exception:
            self.session.rollback()
            raise
        return self._to_entry_read(entry, current_metadata)

    def update_personal_entry(
        self,
        package_id: int,
        workflow_key: str,
        entry_id: int,
        *,
        name: str | None | _UnsetType = _UNSET,
        payload: object | _UnsetType = _UNSET,
        source_kind: str | _UnsetType = _UNSET,
        owner_type: str = LOCAL_RUNTIME_INPUT_OWNER_TYPE,
        owner_id: str = LOCAL_RUNTIME_INPUT_OWNER_ID,
        source_run_id: int | None | _UnsetType = _UNSET,
    ) -> WorkflowPackageRuntimeInputEntryRead:
        package = self._get_package(package_id)
        scope = self._scope(
            package_id=package.id,
            workflow_key=workflow_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        current_metadata = self._current_metadata(package, scope["workflow_key"])
        entry = self.repository.get_runtime_input_personal_entry(**scope, entry_id=entry_id)
        if entry is None:
            raise not_found_error("Workflow package runtime input personal entry")

        fields: dict[str, object] = {}
        if not isinstance(name, _UnsetType):
            fields["name"] = self._normalize_name(name)
        if not isinstance(source_kind, _UnsetType):
            fields["source_kind"] = self._normalize_source_kind(source_kind)
        if not isinstance(source_run_id, _UnsetType):
            fields["source_run_id"] = self._normalize_source_run_id(source_run_id)
        if not isinstance(payload, _UnsetType):
            current_metadata = self._require_current_metadata(package, scope["workflow_key"])
            safe_payload = validate_runtime_input_payload_safety(payload)
            fields["payload"] = deepcopy(
                self._canonical_personal_payload(current_metadata, safe_payload)
            )
            fields.update(self._metadata_fields(current_metadata))
        if not fields:
            return self._to_entry_read(entry, current_metadata)

        try:
            updated = self.repository.update_runtime_input_personal_entry(
                **scope,
                entry_id=entry_id,
                **fields,
            )
            if updated is None:
                raise not_found_error("Workflow package runtime input personal entry")
            self.session.commit()
            self.session.refresh(updated)
        except Exception:
            self.session.rollback()
            raise
        return self._to_entry_read(updated, current_metadata)

    def delete_personal_entry(
        self,
        package_id: int,
        workflow_key: str,
        entry_id: int,
        *,
        owner_type: str = LOCAL_RUNTIME_INPUT_OWNER_TYPE,
        owner_id: str = LOCAL_RUNTIME_INPUT_OWNER_ID,
    ) -> None:
        package = self._get_package(package_id)
        scope = self._scope(
            package_id=package.id,
            workflow_key=workflow_key,
            owner_type=owner_type,
            owner_id=owner_id,
        )
        try:
            deleted = self.repository.delete_runtime_input_personal_entry(
                **scope,
                entry_id=entry_id,
            )
            if not deleted:
                raise not_found_error("Workflow package runtime input personal entry")
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

    def append_history_entry_for_launch(
        self,
        package_id: int,
        workflow_key: str,
        *,
        payload: object,
        source_run_id: int,
    ) -> WorkflowPackageRuntimeInputEntry:
        package = self._get_package(package_id)
        scope = self._scope(
            package_id=package.id,
            workflow_key=workflow_key,
            owner_type=LOCAL_RUNTIME_INPUT_OWNER_TYPE,
            owner_id=LOCAL_RUNTIME_INPUT_OWNER_ID,
        )
        current_metadata = self._require_current_metadata(package, scope["workflow_key"])
        return self._append_history_entry_in_current_transaction(
            scope=scope,
            payload=validate_runtime_input_payload_safety(payload),
            source_kind="launch",
            current_metadata=current_metadata,
            source_run_id=source_run_id,
        )

    def _append_history_entry_in_current_transaction(
        self,
        *,
        scope: _RuntimeInputScope,
        payload: dict[str, Any],
        source_kind: str,
        current_metadata: RuntimeInputWorkflowMetadata,
        source_run_id: int | None,
    ) -> WorkflowPackageRuntimeInputEntry:
        self._acquire_scope_lock(scope, slot="history")
        entry = self.repository.append_runtime_input_history_entry(
            **scope,
            payload=deepcopy(payload),
            source_kind=self._normalize_source_kind(source_kind),
            source_run_id=self._normalize_source_run_id(source_run_id),
            **self._metadata_fields(current_metadata),
        )
        self.session.flush()
        _ = self.repository.trim_runtime_input_history_overflow(**scope)
        return entry

    def _get_package(self, package_id: int) -> WorkflowPackage:
        package = self.repository.get(package_id)
        if package is None:
            raise not_found_error("Workflow package")
        return package

    def _acquire_scope_lock(
        self,
        scope: _RuntimeInputScope,
        *,
        slot: WorkflowPackageRuntimeInputSlot,
    ) -> None:
        key_part_1, key_part_2 = self._scope_lock_key_parts(scope, slot=slot)
        statement = text(
            "SELECT pg_advisory_xact_lock(:runtime_input_scope_lock_1, "
            + ":runtime_input_scope_lock_2)"
        )
        _ = self.session.execute(
            statement,
            {
                "runtime_input_scope_lock_1": key_part_1,
                "runtime_input_scope_lock_2": key_part_2,
            },
        )

    @staticmethod
    def _scope_lock_key_parts(
        scope: _RuntimeInputScope,
        *,
        slot: WorkflowPackageRuntimeInputSlot,
    ) -> tuple[int, int]:
        raw_key = "\0".join(
            (
                "workflow_package_runtime_input_registry",
                str(scope["package_id"]),
                scope["workflow_key"],
                scope["owner_type"],
                scope["owner_id"],
                slot,
            )
        )
        digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
        return (
            int.from_bytes(digest[:4], byteorder="big", signed=True),
            int.from_bytes(digest[4:8], byteorder="big", signed=True),
        )

    def _enforce_personal_limit(self, scope: _RuntimeInputScope) -> None:
        current_count = self.repository.count_runtime_input_personal_entries(**scope)
        if current_count < RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT:
            return
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="workflow_package_runtime_input_personal_limit_reached",
            message="Workflow package runtime input personal limit reached",
            details=[
                {
                    "field": "personal",
                    "issue": "Personal runtime input entries are limited to 20 per scope",
                    "limit": RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT,
                    "actual": current_count,
                }
            ],
        )

    def _scope(
        self,
        *,
        package_id: int,
        workflow_key: str,
        owner_type: str,
        owner_id: str,
    ) -> _RuntimeInputScope:
        return {
            "package_id": package_id,
            "workflow_key": self._normalize_text(
                workflow_key,
                field="workflowKey",
                max_length=120,
            ),
            "owner_type": self._normalize_text(
                owner_type,
                field="ownerType",
                max_length=40,
            ),
            "owner_id": self._normalize_text(
                owner_id,
                field="ownerId",
                max_length=120,
            ),
        }

    @staticmethod
    def _normalize_text(value: object, *, field: str, max_length: int) -> str:
        if not isinstance(value, str):
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": field, "issue": "Value must be a string"}],
            )
        normalized = value.strip()
        if not normalized:
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": field, "issue": "Value is required"}],
            )
        if len(normalized) > max_length:
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [
                    {
                        "field": field,
                        "issue": f"Value must be at most {max_length} characters",
                    }
                ],
            )
        return normalized

    @classmethod
    def _normalize_source_kind(cls, value: object) -> str:
        return cls._normalize_text(value, field="sourceKind", max_length=40)

    @staticmethod
    def _normalize_name(value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": "name", "issue": "Name must be a string"}],
            )
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > 200:
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": "name", "issue": "Name must be at most 200 characters"}],
            )
        return normalized

    @staticmethod
    def _normalize_source_run_id(value: object) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": "sourceRunId", "issue": "Source run id must be an integer"}],
            )
        if value < 1:
            raise validation_error(
                _RUNTIME_INPUT_ENTRY_VALIDATION_MESSAGE,
                [{"field": "sourceRunId", "issue": "Source run id must be positive"}],
            )
        return value

    def _canonical_personal_payload(
        self,
        current_metadata: RuntimeInputWorkflowMetadata,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return validate_run_input_payload(
            schema_compiler=self.schema_compiler,
            input_schema=current_metadata.input_schema,
            input_payload=payload,
            candidate_key=(
                "workflow_package_runtime_input_" f"{current_metadata.schema_fingerprint[:12]}"
            ),
            resource_name="workflowPackage",
        )

    @staticmethod
    def _metadata_fields(metadata: RuntimeInputWorkflowMetadata) -> _RuntimeInputMetadataFields:
        return {
            "manifest_hash": metadata.manifest_hash,
            "compiled_hash": metadata.compiled_hash,
            "schema_fingerprint": metadata.schema_fingerprint,
            "input_schema_snapshot": cast(dict[str, object], deepcopy(metadata.input_schema)),
        }

    @staticmethod
    def _current_metadata(
        package: WorkflowPackage,
        workflow_key: str,
    ) -> RuntimeInputWorkflowMetadata | None:
        return build_runtime_input_current_metadata(
            workflow_key=workflow_key,
            manifest_hash=package.manifest_hash,
            compiled_hash=package.compiled_hash,
            compiled_plan=package.compiled_plan,
        )

    def _require_current_metadata(
        self,
        package: WorkflowPackage,
        workflow_key: str,
    ) -> RuntimeInputWorkflowMetadata:
        current_metadata = self._current_metadata(package, workflow_key)
        if current_metadata is None:
            raise not_found_error("Workflow package workflow")
        return current_metadata

    @staticmethod
    def _to_entry_read(
        entry: WorkflowPackageRuntimeInputEntry,
        current_metadata: RuntimeInputWorkflowMetadata | None,
    ) -> WorkflowPackageRuntimeInputEntryRead:
        input_schema_snapshot = (
            deepcopy(entry.input_schema_snapshot)
            if isinstance(entry.input_schema_snapshot, dict)
            else None
        )
        stored_metadata = RuntimeInputStoredMetadata(
            workflow_key=entry.workflow_key,
            manifest_hash=entry.manifest_hash,
            compiled_hash=entry.compiled_hash,
            schema_fingerprint=entry.schema_fingerprint,
        )
        return WorkflowPackageRuntimeInputEntryRead(
            id=entry.id,
            package_id=entry.package_id,
            workflow_key=entry.workflow_key,
            slot=cast(WorkflowPackageRuntimeInputSlot, entry.slot),
            name=entry.name,
            payload=deepcopy(entry.payload),
            source_kind=entry.source_kind,
            manifest_hash=entry.manifest_hash,
            compiled_hash=entry.compiled_hash,
            schema_fingerprint=entry.schema_fingerprint,
            input_schema_snapshot=input_schema_snapshot,
            source_run_id=entry.source_run_id,
            stale=evaluate_runtime_input_staleness(stored_metadata, current_metadata),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


__all__ = [
    "LOCAL_RUNTIME_INPUT_OWNER_ID",
    "LOCAL_RUNTIME_INPUT_OWNER_TYPE",
    "RUNTIME_INPUT_PERSONAL_ENTRY_LIMIT",
    "WorkflowPackageRuntimeInputEntryRead",
    "WorkflowPackageRuntimeInputRegistryRead",
    "WorkflowPackageRuntimeInputRegistryService",
    "WorkflowPackageRuntimeInputSlot",
]
