from __future__ import annotations

from typing import Any

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session, sessionmaker

from app.models.run import Run, RunWorkflowPackageSnapshot
from app.models.run_agent_invocation import RunAgentInvocation
from app.models.run_step import RunStep
from app.models.workflow_package import WorkflowPackage
from app.repositories.run import RunRepository
from app.repositories.workflow_checkpoints import WorkflowCheckpointRepository
from app.repositories.workflow_memory import WorkflowMemoryRepository
from app.repositories.workflow_package import WorkflowPackageRepository
from app.services.run_read_projection import RunReadProjection


def _seed_package_run(session: Session, *, package_key: str = "projection_memory_pkg") -> Run:
    package = WorkflowPackage(
        key=package_key,
        name="Projection Memory Package",
        description="Run read projection fixture.",
        manifest_source="apiVersion: signaldeck.workflowPackage/v1\nkind: WorkflowPackage\n",
        manifest_hash="a" * 64,
        compiled_hash="b" * 64,
        package_definition={"metadata": {"key": package_key}},
        compiled_plan={"outputSchemas": [{"key": "summary_output"}]},
        extension_dependencies=[],
    )
    session.add(package)
    session.flush()

    run = Run(
        target_kind="workflowPackage",
        target_id=package.id,
        target_key=package.key,
        target_version=1,
        workflow_package_id=package.id,
        workflow_package_key=package.key,
        workflow_package_workflow_key="runtime_workflow",
        input={"ticker": "MSFT"},
        status="succeeded",
        final_output={"summary": "done"},
        total_tokens=3,
        inherited_tokens=0,
        executed_tokens=3,
    )
    run.workflow_package_snapshot = RunWorkflowPackageSnapshot(
        workflow_package_id=package.id,
        workflow_package_key=package.key,
        workflow_package_name=package.name,
        workflow_package_description=package.description,
        workflow_package_status=None,
        workflow_key="runtime_workflow",
        workflow_name="Runtime Workflow",
        workflow_description="",
        manifest_hash=package.manifest_hash,
        compiled_hash=package.compiled_hash,
        manifest_source=package.manifest_source,
        package_definition=package.package_definition,
        compiled_plan=package.compiled_plan,
        extension_dependencies=[],
        local_resource_refs={"outputSchemas": ["summary_output"]},
        input_schema={"type": "object"},
        launch_parameters={"ticker": "MSFT"},
        resolved_model_connections=[],
        preflight_summary={"ready": True, "blockingErrors": [], "warnings": []},
    )
    session.add(run)
    session.flush()

    step = RunStep(
        run_id=run.id,
        step_index=1,
        status="succeeded",
        origin="planned",
        graph_metadata={"nodeId": "package_analysis"},
    )
    session.add(step)
    session.flush()

    session.add(
        RunAgentInvocation(
            run_step_id=step.id,
            run_id=run.id,
            step_index=1,
            slot="analysis",
            position=0,
            agent_id=1,
            agent_key="package_analyst",
            agent_version=1,
            output_schema_id=1,
            output_schema_version=1,
            input_mode="wired",
            graph_metadata={
                "modelGateway": {
                    "workflowMemory": {
                        "enabled": True,
                        "scope": {
                            "packageKey": package.key,
                            "workflowKey": "runtime_workflow",
                            "agentKey": "package_analyst",
                            "stepId": "package_analysis",
                            "namespace": "research",
                        },
                        "runId": run.id,
                        "invocationId": "1",
                        "policySnapshot": {
                            "enabled": True,
                            "writes": {"default_decision": "commit"},
                        },
                        "contextItemIds": ["mem-context"],
                        "checkpointIds": ["checkpoint-begin"],
                        "completion": {
                            "proposalCount": 2,
                            "decisionCount": 2,
                            "rejectedCount": 0,
                        },
                    }
                }
            },
            optional=False,
            status="succeeded",
            resolved_input={"ticker": "MSFT"},
            resolved_input_origin="derived",
            output={"summary": "done"},
            output_origin="executed",
            tokens=3,
        )
    )
    session.commit()
    return run


def _projection(session: Session) -> RunReadProjection:
    def snapshot_for_run(run: Run) -> RunWorkflowPackageSnapshot:
        assert run.workflow_package_snapshot is not None
        return run.workflow_package_snapshot

    return RunReadProjection(
        session=session,
        run_repository=RunRepository(session),
        workflow_package_repository=WorkflowPackageRepository(session),
        workflow_package_snapshot_for_run=snapshot_for_run,
    )


def _run_detail(session: Session, run_id: int) -> dict[str, Any]:
    run = RunRepository(session).get_detail(run_id)
    assert run is not None
    return _projection(session).to_read_model(run).model_dump(mode="json", by_alias=True)


def test_no_memory_run_returns_empty_workflow_memory_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_package_run(session, package_key="projection_no_memory_pkg")
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run.id).one()
        invocation.graph_metadata = None
        session.commit()

        detail = _run_detail(session, run.id)

    assert detail["workflowMemoryEvidence"] == {
        "injections": [],
        "proposals": [],
        "decisions": [],
        "quarantines": [],
        "checkpoints": [],
        "auditEvents": [],
    }


def test_run_detail_exposes_workflow_memory_middleware_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_package_run(session)
        memory_repo = WorkflowMemoryRepository(session)
        checkpoint_repo = WorkflowCheckpointRepository(session)
        _ = checkpoint_repo.create_checkpoint(
            checkpoint_id="checkpoint-begin",
            run_id=run.id,
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            checkpoint_type="step_begin",
            sequence=1001,
            state_json={"status": "running"},
            retention="run_lifecycle",
            step_id="package_analysis",
            metadata_json={"phase": "begin_step"},
        )
        committed_proposal = memory_repo.create_proposal(
            proposal_id="proposal-commit",
            run_id=run.id,
            invocation_id="1",
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            agent_key="package_analyst",
            step_id="package_analysis",
            namespace="research",
            kind="fact",
            content_json={"text": "Revenue accelerated."},
            reason="runtime proposal",
            source_output_path="steps.1.analysis.output.memoryProposals",
            status="committed",
        )
        commit_decision = memory_repo.record_decision(
            decision_id="decision-commit",
            proposal=committed_proposal,
            decision="commit",
            reason_code="auto_commit_allowed",
            reason="Policy allowed automatic commit.",
            decided_by="policy",
            policy_snapshot_json={"enabled": True},
        )
        committed_item = memory_repo.create_memory_item(
            memory_id="workflow-memory-committed",
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            agent_key="package_analyst",
            step_id="package_analysis",
            namespace="research",
            kind="fact",
            content_json={"text": "Revenue accelerated."},
            summary="Revenue accelerated.",
            proposal_id=committed_proposal.id,
            decision_id=commit_decision.id,
            run_id=run.id,
            invocation_id="1",
        )
        committed_memory_id = committed_item.memory_id
        _ = memory_repo.record_audit_event(
            event_type="memory_policy_commit",
            target_type="proposal",
            target_id=committed_proposal.proposal_id,
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            agent_key="package_analyst",
            step_id="package_analysis",
            run_id=run.id,
            invocation_id="1",
            event_json={"decisionId": commit_decision.decision_id},
        )
        quarantined_proposal = memory_repo.create_proposal(
            proposal_id="proposal-quarantine",
            run_id=run.id,
            invocation_id="1",
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            agent_key="package_analyst",
            step_id="package_analysis",
            namespace="research",
            kind="fact",
            content_json={"text": "sk-test_secret"},
            detectors_json={"secrets": [{"detector": "api_key"}]},
            status="quarantined",
        )
        quarantine_decision = memory_repo.record_decision(
            decision_id="decision-quarantine",
            proposal=quarantined_proposal,
            decision="quarantine",
            reason_code="secret_detected",
            reason="Detector policy quarantined the proposal.",
            decided_by="policy",
            policy_snapshot_json={"enabled": True},
        )
        _ = memory_repo.quarantine_proposal(
            proposal=quarantined_proposal,
            reason_code="secret_detected",
            reason="Detector policy quarantined the proposal.",
            run_id=run.id,
            invocation_id="1",
            detectors_json={"secrets": [{"detector": "api_key"}]},
        )
        _ = memory_repo.record_audit_event(
            event_type="memory_policy_quarantine",
            target_type="proposal",
            target_id=quarantined_proposal.proposal_id,
            package_key="projection_memory_pkg",
            workflow_key="runtime_workflow",
            agent_key="package_analyst",
            step_id="package_analysis",
            run_id=run.id,
            invocation_id="1",
            event_json={"decisionId": quarantine_decision.decision_id},
        )
        session.commit()

        detail = _run_detail(session, run.id)

    evidence = detail["workflowMemoryEvidence"]
    assert evidence["injections"][0]["contextItemIds"] == ["mem-context"]
    assert evidence["injections"][0]["policySnapshot"] == {
        "enabled": True,
        "writes": {"default_decision": "commit"},
    }
    assert evidence["injections"][0]["completion"] == {
        "proposalCount": 2,
        "decisionCount": 2,
        "rejectedCount": 0,
    }
    assert [proposal["proposalId"] for proposal in evidence["proposals"]] == [
        "proposal-commit",
        "proposal-quarantine",
    ]
    assert evidence["proposals"][0]["activeMemoryIds"] == [committed_memory_id]
    assert [(item["proposalId"], item["decision"]) for item in evidence["decisions"]] == [
        ("proposal-commit", "commit"),
        ("proposal-quarantine", "quarantine"),
    ]
    assert evidence["quarantines"][0]["proposalId"] == "proposal-quarantine"
    assert evidence["quarantines"][0]["reasonCode"] == "secret_detected"
    assert evidence["checkpoints"][0]["checkpointId"] == "checkpoint-begin"
    assert evidence["checkpoints"][0]["checkpointType"] == "step_begin"
    assert [event["event"]["decisionId"] for event in evidence["auditEvents"]] == [
        "decision-commit",
        "decision-quarantine",
    ]


def test_projection_omits_legacy_run_memory_event_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        run = _seed_package_run(session, package_key="projection_legacy_event_pkg")
        invocation = session.query(RunAgentInvocation).filter_by(run_id=run.id).one()
        invocation.graph_metadata = None
        session.commit()
        table_names = set(sqlalchemy_inspect(session.get_bind()).get_table_names())
        assert "run_memory_events" not in table_names

        detail = _run_detail(session, run.id)

    assert "memoryEvents" not in detail
    assert "memoryArtifacts" not in detail
    assert detail["workflowMemoryEvidence"]["injections"] == []
