from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class WorkflowPackageVersionModelConnection(IdMixin, Base):
    __tablename__ = "workflow_package_version_model_connections"
    __table_args__ = (
        UniqueConstraint(
            "workflow_package_version_id",
            "model_connection_id",
            name="uq_wpv_model_connections_version_connection",
        ),
        Index(
            "ix_wpv_model_connections_version",
            "workflow_package_version_id",
        ),
        Index("ix_wpv_model_connections_connection", "model_connection_id"),
    )

    workflow_package_version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_package_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    model_connection_id: Mapped[int] = mapped_column(
        ForeignKey("model_connections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_connection_key: Mapped[str] = mapped_column(String(120), nullable=False)


class WorkflowAgentRef(IdMixin, Base):
    __tablename__ = "workflow_agent_refs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "agent_id", name="uq_workflow_agent_refs_workflow_agent"),
        Index("ix_workflow_agent_refs_workflow", "workflow_id"),
        Index("ix_workflow_agent_refs_agent", "agent_id"),
    )

    workflow_id: Mapped[int] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"),
        nullable=False,
    )


class AgentCapabilityRef(IdMixin, Base):
    __tablename__ = "agent_capability_refs"
    __table_args__ = (
        UniqueConstraint(
            "agent_id",
            "capability_id",
            name="uq_agent_capability_refs_agent_capability",
        ),
        Index("ix_agent_capability_refs_agent", "agent_id"),
        Index("ix_agent_capability_refs_capability", "capability_id"),
    )

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    capability_id: Mapped[int] = mapped_column(
        ForeignKey("capabilities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    capability_key: Mapped[str] = mapped_column(String(120), nullable=False)


class AgentMcpServerRef(IdMixin, Base):
    __tablename__ = "agent_mcp_server_refs"
    __table_args__ = (
        UniqueConstraint("agent_id", "mcp_server_id", name="uq_agent_mcp_server_refs_agent_server"),
        Index("ix_agent_mcp_server_refs_agent", "agent_id"),
        Index("ix_agent_mcp_server_refs_server", "mcp_server_id"),
    )

    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
    )
    mcp_server_id: Mapped[int] = mapped_column(
        ForeignKey("mcp_servers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    mcp_server_key: Mapped[str] = mapped_column(String(120), nullable=False)
