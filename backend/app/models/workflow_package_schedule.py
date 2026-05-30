from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.formatting import utcnow
from app.models.base import Base, IdMixin


class WorkflowPackageSchedule(IdMixin, Base):
    __tablename__ = "workflow_package_schedules"
    __table_args__ = (
        CheckConstraint(
            "status IN ('enabled', 'paused', 'archived')",
            name="ck_workflow_package_schedules_status",
        ),
        CheckConstraint(
            "overlap_policy IN ('skip', 'queue')",
            name="ck_workflow_package_schedules_overlap_policy",
        ),
        CheckConstraint(
            "misfire_policy IN ('skip', 'catchUpOne')",
            name="ck_workflow_package_schedules_misfire_policy",
        ),
        CheckConstraint(
            "misfire_grace_seconds >= 0",
            name="ck_workflow_package_schedules_misfire_grace_non_negative",
        ),
        Index("ix_workflow_package_schedules_package", "package_id"),
        Index("ix_workflow_package_schedules_package_workflow", "package_id", "workflow_key"),
        Index("ix_workflow_package_schedules_status_next_fire", "status", "next_fire_at", "id"),
        Index("ix_workflow_package_schedules_next_fire", "next_fire_at"),
    )

    package_id: Mapped[int] = mapped_column(
        ForeignKey(
            "workflow_packages.id",
            ondelete="CASCADE",
            name="fk_workflow_package_schedules_package_id",
        ),
        nullable=False,
    )
    workflow_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="enabled", server_default="enabled"
    )
    timezone: Mapped[str] = mapped_column(String(120), nullable=False)
    recurrence: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_fire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overlap_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="skip",
        server_default="skip",
    )
    misfire_policy: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="catchUpOne",
        server_default="catchUpOne",
    )
    misfire_grace_seconds: Mapped[int] = mapped_column(
        nullable=False, default=86400, server_default="86400"
    )
    input_template: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    template_vars: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


class WorkflowPackageScheduleFire(IdMixin, Base):
    __tablename__ = "workflow_package_schedule_fires"
    __table_args__ = (
        UniqueConstraint(
            "schedule_id",
            "fire_key",
            name="uq_workflow_package_schedule_fires_schedule_fire_key",
        ),
        CheckConstraint(
            "status IN ('pending', 'queued', 'skipped', 'failed')",
            name="ck_workflow_package_schedule_fires_status",
        ),
        CheckConstraint(
            "reason IN ('scheduled', 'manual')",
            name="ck_workflow_package_schedule_fires_reason",
        ),
        Index("ix_workflow_package_schedule_fires_schedule", "schedule_id"),
        Index("ix_workflow_package_schedule_fires_schedule_status", "schedule_id", "status"),
        Index("ix_workflow_package_schedule_fires_scheduled_for", "scheduled_for"),
        Index("ix_workflow_package_schedule_fires_status", "status"),
    )

    schedule_id: Mapped[int] = mapped_column(
        ForeignKey(
            "workflow_package_schedules.id",
            ondelete="CASCADE",
            name="fk_workflow_package_schedule_fires_schedule_id",
        ),
        nullable=False,
    )
    fire_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="scheduled",
        server_default="scheduled",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_local_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    scheduled_local_time: Mapped[str | None] = mapped_column(String(8), nullable=True)
    scheduled_local_datetime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    materialized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rendered_parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sql_text("'{}'::jsonb"),
    )
    skip_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
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
