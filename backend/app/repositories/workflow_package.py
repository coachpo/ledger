# pyright: reportExplicitAny=false
from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import delete, func, select
from sqlalchemy.sql.elements import ColumnElement

from app.models.workflow_package import WorkflowPackage, WorkflowPackageRuntimeInputEntry
from app.repositories.base import BaseRepository


class WorkflowPackageRepository(BaseRepository[WorkflowPackage]):
    model: ClassVar[type[WorkflowPackage]] = WorkflowPackage
    runtime_input_model: ClassVar[type[WorkflowPackageRuntimeInputEntry]] = (
        WorkflowPackageRuntimeInputEntry
    )
    runtime_input_history_limit: ClassVar[int] = 20

    def list_packages(self) -> list[WorkflowPackage]:
        statement = select(self.model).order_by(self.model.key.asc(), self.model.id.asc())
        return self._list(statement)

    def get_by_key(self, key: str) -> WorkflowPackage | None:
        statement = select(self.model).where(self.model.key == key)
        statement = statement.order_by(self.model.id.asc())
        return self._get_by_statement(statement)

    def create_package(
        self,
        *,
        key: str,
        name: str,
        description: str = "",
        manifest_source: str,
        manifest_hash: str,
        package_definition: dict[str, Any],
        compiled_plan: dict[str, Any],
        compiled_hash: str,
        extension_dependencies: list[dict[str, Any]] | None = None,
    ) -> WorkflowPackage:
        package = WorkflowPackage(
            key=key,
            name=name,
            description=description,
            manifest_source=manifest_source,
            manifest_hash=manifest_hash,
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=compiled_hash,
            extension_dependencies=list(extension_dependencies or []),
        )
        return self.add(package)

    def update_package(self, package: WorkflowPackage, **fields: object) -> WorkflowPackage:
        for field_name, value in fields.items():
            setattr(package, field_name, value)
        return self.add(package)

    def list_runtime_input_preset_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> list[WorkflowPackageRuntimeInputEntry]:
        entry_model = self.runtime_input_model
        statement = (
            select(entry_model)
            .where(
                *self._runtime_input_scope_filters(
                    package_id=package_id,
                    workflow_key=workflow_key,
                    slot="preset",
                )
            )
            .order_by(entry_model.updated_at.desc(), entry_model.id.desc())
        )
        return list(self.session.scalars(statement))

    def list_runtime_input_history_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> list[WorkflowPackageRuntimeInputEntry]:
        entry_model = self.runtime_input_model
        statement = (
            select(entry_model)
            .where(
                *self._runtime_input_scope_filters(
                    package_id=package_id,
                    workflow_key=workflow_key,
                    slot="history",
                )
            )
            .order_by(entry_model.created_at.desc(), entry_model.id.desc())
        )
        return list(self.session.scalars(statement))

    def count_runtime_input_preset_entries(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> int:
        entry_model = self.runtime_input_model
        statement = select(func.count(entry_model.id)).where(
            *self._runtime_input_scope_filters(
                package_id=package_id,
                workflow_key=workflow_key,
                slot="preset",
            )
        )
        return int(self.session.scalar(statement) or 0)

    def create_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        name: str | None,
        payload: dict[str, object],
        source_kind: str,
        manifest_hash: str,
        compiled_hash: str,
        schema_fingerprint: str,
        input_schema_snapshot: dict[str, object] | None,
        source_run_id: int | None = None,
    ) -> WorkflowPackageRuntimeInputEntry:
        entry = self.runtime_input_model(
            package_id=package_id,
            workflow_key=workflow_key,
            slot="preset",
            name=name,
            payload=payload,
            source_kind=source_kind,
            manifest_hash=manifest_hash,
            compiled_hash=compiled_hash,
            schema_fingerprint=schema_fingerprint,
            input_schema_snapshot=input_schema_snapshot,
            source_run_id=source_run_id,
        )
        self.session.add(entry)
        return entry

    def append_runtime_input_history_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        payload: dict[str, object],
        source_kind: str,
        manifest_hash: str,
        compiled_hash: str,
        schema_fingerprint: str,
        input_schema_snapshot: dict[str, object] | None,
        source_run_id: int | None = None,
    ) -> WorkflowPackageRuntimeInputEntry:
        entry = self.runtime_input_model(
            package_id=package_id,
            workflow_key=workflow_key,
            slot="history",
            name=None,
            payload=payload,
            source_kind=source_kind,
            manifest_hash=manifest_hash,
            compiled_hash=compiled_hash,
            schema_fingerprint=schema_fingerprint,
            input_schema_snapshot=input_schema_snapshot,
            source_run_id=source_run_id,
        )
        self.session.add(entry)
        return entry

    def trim_runtime_input_history_overflow(
        self,
        *,
        package_id: int,
        workflow_key: str,
    ) -> int:
        entry_model = self.runtime_input_model
        scope_filters = self._runtime_input_scope_filters(
            package_id=package_id,
            workflow_key=workflow_key,
            slot="history",
        )
        overflow_ids = list(
            self.session.scalars(
                select(entry_model.id)
                .where(*scope_filters)
                .order_by(entry_model.created_at.desc(), entry_model.id.desc())
                .offset(self.runtime_input_history_limit)
            )
        )
        if not overflow_ids:
            return 0

        statement = (
            delete(entry_model)
            .where(*scope_filters, entry_model.id.in_(overflow_ids))
            .returning(entry_model.id)
        )
        return len(list(self.session.scalars(statement)))

    def get_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
    ) -> WorkflowPackageRuntimeInputEntry | None:
        entry_model = self.runtime_input_model
        statement = select(entry_model).where(
            entry_model.id == entry_id,
            *self._runtime_input_scope_filters(
                package_id=package_id,
                workflow_key=workflow_key,
                slot="preset",
            ),
        )
        return self.session.scalar(statement)

    def update_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
        **fields: object,
    ) -> WorkflowPackageRuntimeInputEntry | None:
        entry = self.get_runtime_input_preset_entry(
            package_id=package_id,
            workflow_key=workflow_key,
            entry_id=entry_id,
        )
        if entry is None:
            return None

        allowed_fields = {
            "name",
            "payload",
            "source_kind",
            "manifest_hash",
            "compiled_hash",
            "schema_fingerprint",
            "input_schema_snapshot",
            "source_run_id",
        }
        unknown_fields = set(fields) - allowed_fields
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unsupported runtime input update fields: {unknown}")

        for field_name, value in fields.items():
            setattr(entry, field_name, value)
        self.session.add(entry)
        return entry

    def delete_runtime_input_preset_entry(
        self,
        *,
        package_id: int,
        workflow_key: str,
        entry_id: int,
    ) -> bool:
        entry = self.get_runtime_input_preset_entry(
            package_id=package_id,
            workflow_key=workflow_key,
            entry_id=entry_id,
        )
        if entry is None:
            return False
        self.session.delete(entry)
        return True

    @classmethod
    def _runtime_input_scope_filters(
        cls,
        *,
        package_id: int,
        workflow_key: str,
        slot: str,
    ) -> tuple[ColumnElement[bool], ...]:
        entry_model = cls.runtime_input_model
        return (
            entry_model.package_id == package_id,
            entry_model.workflow_key == workflow_key,
            entry_model.slot == slot,
        )
