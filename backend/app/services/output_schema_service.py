from __future__ import annotations

from typing import Any

from fastapi import status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import ApiError, business_rule_error, not_found_error, validation_error
from app.models.output_schema import OutputSchema
from app.repositories.output_schema import OutputSchemaRepository
from app.schemas.output_schema import (
    OutputSchemaBuilderNode,
    OutputSchemaDraftCreate,
    OutputSchemaDraftUpdate,
    OutputSchemaKind,
    OutputSchemaListRead,
    OutputSchemaRead,
    OutputSchemaStatus,
)
from app.services.output_schema_compiler import (
    OutputSchemaCompiler,
    OutputSchemaCompilerError,
    OutputSchemaValidationFailure,
    PreparedOutputSchema,
)


class OutputSchemaService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = OutputSchemaRepository(session)
        self.compiler = OutputSchemaCompiler(self.repository)

    def list_schemas(
        self,
        *,
        status_filter: OutputSchemaStatus | None = None,
        kind: OutputSchemaKind | None = None,
    ) -> OutputSchemaListRead:
        items = self.repository.list_latest_versions(
            status=status_filter.value if status_filter is not None else None,
            kind=kind.value if kind is not None else None,
        )
        return OutputSchemaListRead(items=[self._to_read_model(item) for item in items])

    def get_schema(self, schema_id: int) -> OutputSchemaRead:
        return self._to_read_model(self._get_model(schema_id))

    def create_draft(self, payload: OutputSchemaDraftCreate) -> OutputSchemaRead:
        if self.repository.get_draft_by_key(payload.key) is not None:
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="output_schema_duplicate_draft",
                message="A draft output schema already exists for this key",
            )

        prepared = self._normalize_payload(builder=payload.builder, json_schema=payload.json_schema)
        schema = OutputSchema(
            key=payload.key,
            version=self._next_version(payload.key),
            status=OutputSchemaStatus.DRAFT.value,
            kind=payload.kind.value,
            name=payload.name,
            description=payload.description,
            json_schema=prepared.json_schema,
            registry_refs=prepared.registry_refs,
        )
        try:
            self.repository.add(schema)
            self.session.commit()
            self.session.refresh(schema)
            self.compiler.clear_caches()
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(schema, prepared=prepared)

    def update_draft(self, schema_id: int, payload: OutputSchemaDraftUpdate) -> OutputSchemaRead:
        source = self._get_model(schema_id)
        self._ensure_status(source, OutputSchemaStatus.DRAFT, action="patch")

        if "builder" in payload.model_fields_set or "json_schema" in payload.model_fields_set:
            prepared = self._normalize_payload(
                builder=payload.builder if "builder" in payload.model_fields_set else None,
                json_schema=(
                    payload.json_schema if "json_schema" in payload.model_fields_set else None
                ),
            )
        else:
            prepared = self._normalize_payload(builder=None, json_schema=source.json_schema)

        updated = OutputSchema(
            key=source.key,
            version=self._next_version(source.key),
            status=OutputSchemaStatus.DRAFT.value,
            kind=source.kind,
            name=payload.name if payload.name is not None else source.name,
            description=(
                payload.description or ""
                if payload.description is not None or "description" in payload.model_fields_set
                else source.description
            ),
            json_schema=prepared.json_schema,
            registry_refs=prepared.registry_refs,
        )

        try:
            source.status = OutputSchemaStatus.ARCHIVED.value
            self.session.flush()
            self.repository.add(updated)
            self.session.commit()
            self.session.refresh(updated)
            self.compiler.clear_caches()
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(updated, prepared=prepared)

    def activate(self, schema_id: int) -> OutputSchemaRead:
        schema = self._get_model(schema_id)
        self._ensure_status(schema, OutputSchemaStatus.DRAFT, action="activate")
        self._ensure_runtime_compiles(schema)

        current_published = self.repository.get_published_by_key(schema.key)
        try:
            if current_published is not None and current_published.id != schema.id:
                current_published.status = OutputSchemaStatus.DEPRECATED.value
                self.session.flush()
            schema.status = OutputSchemaStatus.PUBLISHED.value
            self.session.commit()
            self.session.refresh(schema)
            self.compiler.clear_caches()
        except Exception:
            self.session.rollback()
            raise
        return self._to_read_model(schema)

    def compile_schema_model(self, schema_id: int) -> type[BaseModel]:
        return self.compiler.build_runtime_model(self._get_model(schema_id))

    def _next_version(self, key: str) -> int:
        versions = self.repository.list_versions(key)
        if not versions:
            return 1
        return versions[0].version + 1

    def _get_model(self, schema_id: int) -> OutputSchema:
        schema = self.repository.get(schema_id)
        if schema is None:
            raise not_found_error("Output schema")
        return schema

    def _ensure_status(
        self,
        schema: OutputSchema,
        expected: OutputSchemaStatus,
        *,
        action: str,
    ) -> None:
        if schema.status != expected.value:
            raise business_rule_error(
                f"output_schema_invalid_{action}_transition",
                f"Only {expected.value} output schemas can be used for this action",
            )

    def _normalize_payload(
        self,
        *,
        builder: OutputSchemaBuilderNode | None,
        json_schema: dict[str, Any] | None,
    ) -> PreparedOutputSchema:
        try:
            return self.compiler.normalize_payload(
                builder=builder,
                json_schema=json_schema,
            )
        except OutputSchemaValidationFailure as exc:
            raise validation_error("Output schema validation failed", exc.issues) from exc

    def _ensure_runtime_compiles(self, schema: OutputSchema) -> None:
        try:
            self.compiler.build_runtime_model(schema)
        except OutputSchemaCompilerError as exc:
            raise validation_error(
                "Output schema validation failed",
                [{"field": "jsonSchema", "issue": str(exc)}],
            ) from exc

    def _to_read_model(
        self,
        schema: OutputSchema,
        *,
        prepared: PreparedOutputSchema | None = None,
    ) -> OutputSchemaRead:
        resolved_schema = prepared or self._normalize_payload(
            builder=None,
            json_schema=schema.json_schema,
        )
        return OutputSchemaRead.model_validate(
            {
                "id": schema.id,
                "key": schema.key,
                "version": schema.version,
                "status": schema.status,
                "kind": schema.kind,
                "name": schema.name,
                "description": schema.description,
                "jsonSchema": resolved_schema.json_schema,
                "builder": resolved_schema.builder,
                "registryRefs": resolved_schema.registry_refs,
                "createdAt": schema.created_at,
                "updatedAt": schema.updated_at,
            }
        )


__all__ = ["OutputSchemaService"]
