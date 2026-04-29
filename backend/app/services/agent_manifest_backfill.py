# pyright: reportMissingImports=false

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.agent import (
    AGENT_MANIFEST_API_VERSION,
    AGENT_MANIFEST_COMPILER_VERSION,
    TEMPORARY_AGENT_MANIFEST_SOURCE,
    Agent,
)
from app.models.model_connection import ModelConnection
from app.services.agent_manifest_compiler import AgentManifestCompilerError, compile_agent_manifest
from app.services.agent_manifest_decompiler import (
    AgentManifestDecompilerError,
    decompile_agent_model,
)
from app.services.model_connection_snapshot import (
    build_model_connection_runtime_snapshot,
    parse_model_connection_runtime_snapshot,
)


@dataclass(frozen=True)
class AgentManifestBackfillFailure:
    key: str
    version: int
    message: str


@dataclass(frozen=True)
class AgentManifestBackfillReport:
    total: int
    converted: int
    skipped_already_current: int
    failed: int
    persisted: int
    failures: list[AgentManifestBackfillFailure] = field(default_factory=list)


class AgentManifestBackfillError(RuntimeError):
    def __init__(self, report: AgentManifestBackfillReport) -> None:
        super().__init__("Agent manifest backfill encountered unsupported or lossy rows")
        self.report: AgentManifestBackfillReport = report


class AgentManifestBackfillService:
    def __init__(self, session: Session) -> None:
        self.session: Session = session

    def audit(self, *, persist: bool = False) -> AgentManifestBackfillReport:
        agents = self._list_agents()
        failures: list[AgentManifestBackfillFailure] = []
        converted_rows: list[tuple[Agent, str, str, dict[str, object]]] = []
        skipped_already_current = 0

        for agent in agents:
            try:
                if self._is_already_current(agent):
                    skipped_already_current += 1
                    continue
                result = decompile_agent_model(agent, self.session)
                manifest_hash = self._manifest_hash(result.source)
                model_connection_snapshot = self._build_model_connection_snapshot(agent)
            except (
                AgentManifestCompilerError,
                AgentManifestDecompilerError,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:
                failures.append(
                    AgentManifestBackfillFailure(
                        key=agent.key,
                        version=agent.version,
                        message=str(exc),
                    )
                )
                continue
            converted_rows.append((agent, result.source, manifest_hash, model_connection_snapshot))

        report = AgentManifestBackfillReport(
            total=len(agents),
            converted=len(converted_rows),
            skipped_already_current=skipped_already_current,
            failed=len(failures),
            persisted=0,
            failures=failures,
        )
        if failures:
            self.session.rollback()
            if persist:
                raise AgentManifestBackfillError(report)
            return report
        if not persist:
            self.session.rollback()
            return report

        try:
            for agent, manifest_source, manifest_hash, model_connection_snapshot in converted_rows:
                agent.manifest_api_version = AGENT_MANIFEST_API_VERSION
                agent.manifest_source = manifest_source
                agent.manifest_hash = manifest_hash
                agent.compiler_version = AGENT_MANIFEST_COMPILER_VERSION
                agent.model_connection_snapshot = model_connection_snapshot
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        return AgentManifestBackfillReport(
            total=report.total,
            converted=report.converted,
            skipped_already_current=report.skipped_already_current,
            failed=report.failed,
            persisted=len(converted_rows),
            failures=report.failures,
        )

    def _is_already_current(self, agent: Agent) -> bool:
        if agent.manifest_source == TEMPORARY_AGENT_MANIFEST_SOURCE:
            return False
        if agent.manifest_api_version != AGENT_MANIFEST_API_VERSION:
            return False
        if agent.compiler_version != AGENT_MANIFEST_COMPILER_VERSION:
            return False
        if agent.manifest_hash != self._manifest_hash(agent.manifest_source):
            raise ValueError("Stored manifest hash does not match manifest_source")
        try:
            _ = parse_model_connection_runtime_snapshot(agent.model_connection_snapshot)
        except ValueError:
            return False

        compiled_payload = compile_agent_manifest(agent.manifest_source, self.session)
        canonical_result = decompile_agent_model(agent, self.session)
        if compiled_payload != canonical_result.payload:
            raise AgentManifestDecompilerError(
                "Stored manifest source does not match compiled agent row"
            )
        if agent.manifest_source != canonical_result.source:
            return False
        return True

    def _build_model_connection_snapshot(self, agent: Agent) -> dict[str, object]:
        model_connection = self.session.get(ModelConnection, agent.model_connection_id)
        if model_connection is None:
            raise AgentManifestDecompilerError(
                f"Agent references missing model connection {agent.model_connection_id}"
            )
        return build_model_connection_runtime_snapshot(model_connection)

    def _list_agents(self) -> list[Agent]:
        statement = select(Agent).order_by(
            Agent.key.asc(),
            Agent.version.asc(),
            Agent.id.asc(),
        )
        return list(self.session.scalars(statement))

    @staticmethod
    def _manifest_hash(manifest_source: str) -> str:
        return hashlib.sha256(manifest_source.encode("utf-8")).hexdigest()


__all__ = [
    "AgentManifestBackfillError",
    "AgentManifestBackfillFailure",
    "AgentManifestBackfillReport",
    "AgentManifestBackfillService",
]
