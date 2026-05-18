from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin, TimestampMixin
from app.models.mcp_server import EncryptedJSONB


class WorkflowPackage(IdMixin, Base):
    __tablename__ = "workflow_packages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active')",
            name="ck_workflow_packages_status",
        ),
        Index("ix_workflow_packages_key", "key"),
        Index("ix_workflow_packages_status", "status"),
        Index("uq_workflow_packages_active_key", "key", unique=True),
        Index("ix_workflow_packages_manifest_hash", "manifest_hash"),
        Index("ix_workflow_packages_compiled_hash", "compiled_hash"),
        Index("ix_workflow_packages_last_launched_at", "last_launched_at"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )
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
    validation_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
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
    last_launched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    secret_bindings: Mapped[list[WorkflowPackageSecretBinding]] = relationship(
        "WorkflowPackageSecretBinding",
        back_populates="package",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkflowPackageSecretBinding.key.asc()",
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
