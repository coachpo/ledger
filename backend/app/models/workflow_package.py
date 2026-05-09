from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


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
        Index("ix_workflow_packages_latest_version", "latest_version_id"),
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
    latest_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "workflow_package_versions.id",
            name="fk_workflow_packages_latest_version_id",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    draft_source: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
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

    versions: Mapped[list[WorkflowPackageVersion]] = relationship(
        "WorkflowPackageVersion",
        back_populates="package",
        cascade="all, delete-orphan",
        foreign_keys="WorkflowPackageVersion.package_id",
        passive_deletes=True,
        order_by="WorkflowPackageVersion.version.desc()",
    )
    latest_version: Mapped[WorkflowPackageVersion | None] = relationship(
        "WorkflowPackageVersion",
        foreign_keys=lambda: [WorkflowPackage.latest_version_id],
        post_update=True,
    )


class WorkflowPackageVersion(IdMixin, Base):
    __tablename__ = "workflow_package_versions"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_workflow_package_versions_version_positive"),
        UniqueConstraint(
            "package_id", "version", name="uq_workflow_package_versions_package_version"
        ),
        Index("ix_workflow_package_versions_package", "package_id"),
        Index("ix_workflow_package_versions_manifest_hash", "manifest_hash"),
        Index("ix_workflow_package_versions_compiled_hash", "compiled_hash"),
        Index("ix_workflow_package_versions_launched_at", "launched_at"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_packages.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    manifest_source: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    package_definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_plan: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    package: Mapped[WorkflowPackage] = relationship(
        "WorkflowPackage",
        back_populates="versions",
        foreign_keys=[package_id],
    )
