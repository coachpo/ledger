from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, EncryptedJSONB, IdMixin, TimestampMixin


class WorkflowPackage(IdMixin, Base):
    __tablename__ = "workflow_packages"
    __table_args__ = (
        Index("ix_workflow_packages_key", "key"),
        Index("uq_workflow_packages_key", "key", unique=True),
        Index("ix_workflow_packages_manifest_hash", "manifest_hash"),
        Index("ix_workflow_packages_compiled_hash", "compiled_hash"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    manifest_source: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    package_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extension_dependencies: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
        onupdate=utcnow,
    )

    secret_bindings: Mapped[list[WorkflowPackageSecretBinding]] = relationship(
        "WorkflowPackageSecretBinding",
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkflowPackageSecretBinding.key.asc()",
    )
    runtime_input_entries: Mapped[list[WorkflowPackageRuntimeInputEntry]] = relationship(
        "WorkflowPackageRuntimeInputEntry",
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=(
            "WorkflowPackageRuntimeInputEntry.updated_at.desc(), "
            "WorkflowPackageRuntimeInputEntry.id.desc()"
        ),
    )


class WorkflowPackageSecretBinding(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_package_secret_bindings"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "key",
            name="uq_workflow_package_secret_bindings_package_key",
        ),
        Index("ix_workflow_package_secret_bindings_package", "package_id"),
        Index("ix_workflow_package_secret_bindings_key", "key"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    secret_payload: Mapped[dict[str, Any]] = mapped_column(
        EncryptedJSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )

    package: Mapped[WorkflowPackage] = relationship(
        "WorkflowPackage",
        back_populates="secret_bindings",
    )


class WorkflowPackageRuntimeInputEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "workflow_package_runtime_input_entries"
    __table_args__ = (
        CheckConstraint(
            "slot IN ('history', 'preset')",
            name="ck_workflow_package_runtime_input_entries_slot",
        ),
        CheckConstraint(
            "slot = 'preset' OR name IS NULL",
            name="ck_workflow_package_runtime_input_entries_name_preset_only",
        ),
        Index("ix_workflow_package_runtime_input_entries_package", "package_id"),
        Index(
            "ix_workflow_package_runtime_input_entries_scope_slot_created",
            "package_id",
            "workflow_key",
            "slot",
            "created_at",
            "id",
        ),
        Index(
            "ix_workflow_package_runtime_input_entries_scope_slot_updated",
            "package_id",
            "workflow_key",
            "slot",
            "updated_at",
            "id",
        ),
        Index("ix_workflow_package_runtime_input_entries_source_run", "source_run_id"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey(
            "workflow_packages.id",
            ondelete="CASCADE",
            name="fk_workflow_package_runtime_input_entries_package_id",
        ),
        nullable=False,
    )
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    slot: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    compiled_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_schema_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "runs.id",
            ondelete="SET NULL",
            name="fk_workflow_package_runtime_input_entries_source_run_id",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sql_text("now()"),
        onupdate=utcnow,
    )

    package: Mapped[WorkflowPackage] = relationship(
        "WorkflowPackage",
        back_populates="runtime_input_entries",
    )
