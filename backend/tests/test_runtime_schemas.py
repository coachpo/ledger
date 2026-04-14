from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.runtime import (
    ApprovalSummary,
    CapabilityRef,
    PersonaProfileRef,
    RuntimeArtifactRead,
    RuntimeRunCreate,
    RuntimeRunRead,
    TraceSummary,
)
from app.schemas.studio import CapabilityRegistryEntryRead, WorkflowSpecRead
from app.schemas.tryout import TryoutExecute, TryoutRead


def test_runtime_refs_and_read_models_serialize_camel_case() -> None:
    persona_ref = PersonaProfileRef.model_validate(
        {
            "personaProfileKey": "alpha_persona",
            "personaProfileVersion": 2,
            "canonicalTargetId": "persona:alpha_persona",
            "selectionSource": "workflow_default",
            "parentPersonaProfileRef": {
                "personaProfileKey": "parent_persona",
                "personaProfileVersion": 1,
                "canonicalTargetId": "persona:parent_persona",
            },
        }
    )
    capability_ref = CapabilityRef.model_validate(
        {
            "capabilityKey": "tool.alpha",
            "capabilityVersion": 3,
            "capabilityType": "tool",
            "selectionSource": "step_selection",
            "effectiveApprovalMode": "required",
            "effectiveConfig": {"mode": "fast"},
        }
    )
    run_read = RuntimeRunRead.model_validate(
        {
            "id": 7,
            "status": "WAITING_APPROVAL",
            "callerType": "tryout",
            "callerId": None,
            "callerScopeKey": None,
            "callerIdentityKey": None,
            "executionKind": "single_agent",
            "workflowSpecKey": None,
            "workflowSpecVersion": None,
            "agentSpecKey": "alpha_agent",
            "agentSpecVersion": 1,
            "attemptNumber": 1,
            "expiresAt": "2026-04-13T10:00:00Z",
            "createdAt": "2026-04-13T09:00:00Z",
            "updatedAt": "2026-04-13T09:30:00Z",
            "pendingApprovalIds": [11],
            "traceSummary": {
                "eventCount": 5,
                "toolCallCount": 2,
                "warningCount": 1,
                "lastEventAt": "2026-04-13T09:29:00Z",
            },
            "approvalSummary": {
                "totalCount": 1,
                "pendingCount": 1,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            },
            "terminalErrorCode": None,
            "terminalErrorMessage": None,
        }
    )
    artifact_read = RuntimeArtifactRead.model_validate(
        {
            "runId": 7,
            "entryPromptHash": "a" * 64,
            "fullUserPromptHash": "b" * 64,
            "rawMentionHandles": ["@librarian"],
            "resolvedMentions": [],
            "mentionedTargetOutputs": [],
            "resolvedPersonaProfileRefs": [persona_ref.model_dump(by_alias=True)],
            "resolvedWorkflowAgentRefs": None,
            "resolvedCapabilities": [
                {
                    "capabilityKey": "tool.alpha",
                    "capabilityVersion": 3,
                    "capabilityType": "tool",
                    "approvalMode": "required",
                    "transport": None,
                    "lifecycle": None,
                    "effectiveConfig": {"mode": "fast"},
                }
            ],
            "resolvedBuiltinVersions": [],
            "resolvedRoleVersions": [],
            "resolvedCharacterVersions": [],
            "resolvedBundleVersions": [],
            "resolvedToolVersions": [],
            "resolvedConnectorVersions": [],
            "traceSummary": run_read.trace_summary.model_dump(by_alias=True),
            "approvalSummary": run_read.approval_summary.model_dump(by_alias=True),
            "terminalErrorCode": "adapter_failure",
            "terminalErrorMessage": "Execution failed",
        }
    )
    tryout_read = TryoutRead.model_validate(
        {
            "runId": 7,
            "status": "WAITING_APPROVAL",
            "finalOutput": None,
            "reportMarkdown": None,
            "traceSummary": run_read.trace_summary.model_dump(by_alias=True),
            "approvalSummary": run_read.approval_summary.model_dump(by_alias=True),
            "expiresAt": "2026-04-13T10:00:00Z",
            "terminalErrorCode": None,
            "terminalErrorMessage": None,
        }
    )

    persona_payload = persona_ref.model_dump(mode="json", by_alias=True)
    capability_payload = capability_ref.model_dump(mode="json", by_alias=True)
    run_payload = run_read.model_dump(mode="json", by_alias=True)
    artifact_payload = artifact_read.model_dump(mode="json", by_alias=True)
    tryout_payload = tryout_read.model_dump(mode="json", by_alias=True)

    assert persona_payload["personaProfileKey"] == "alpha_persona"
    assert persona_payload["parentPersonaProfileRef"]["personaProfileKey"] == "parent_persona"
    assert capability_payload["effectiveApprovalMode"] == "required"
    assert run_payload["runId"] == 7
    assert run_payload["traceSummary"]["eventCount"] == 5
    assert artifact_payload["terminalError"] == {
        "code": "adapter_failure",
        "message": "Execution failed",
    }
    assert tryout_payload["approvalSummary"]["pendingCount"] == 1


def test_runtime_create_tryout_execute_and_studio_read_contracts_validate() -> None:
    runtime_create = RuntimeRunCreate.model_validate(
        {
            "callerType": "api",
            "callerId": 9,
            "callerScopeKey": "adhoc-1",
            "executionKind": "workflow",
            "workflowSpecKey": "alpha_workflow",
            "inputs": {" ticker ": " AAPL ", "empty": "   "},
            "personaProfileRefs": [{"personaProfileKey": "alpha_persona"}],
        }
    )
    tryout_execute = TryoutExecute.model_validate(
        {
            "agentSpecKey": "alpha_agent",
            "inputs": {"ticker": "MSFT"},
            "persistRun": False,
        }
    )
    workflow_read = WorkflowSpecRead.model_validate(
        {
            "id": 1,
            "key": "alpha_workflow",
            "version": 2,
            "origin": "managed",
            "status": "DRAFT",
            "name": "Alpha Workflow",
            "graphDefinition": {
                "entryStepKey": "step-1",
                "steps": [{"stepKey": "step-1", "agentSpecKey": "alpha_agent"}],
            },
            "finalOutputContract": {"kind": "markdown", "schema": None, "description": "Output"},
            "mentionPolicy": {
                "version": 1,
                "allow_characters": False,
                "allowed_builtin_handles": ["librarian"],
            },
            "executionMode": None,
            "defaultToolIds": [],
            "allowedCapabilityBundleKeys": [],
            "connectorIds": [],
            "reviewMode": None,
            "approvalPolicyOverrides": [],
            "createdAt": "2026-04-13T09:00:00Z",
            "updatedAt": "2026-04-13T09:30:00Z",
        }
    )
    capability_read = CapabilityRegistryEntryRead.model_validate(
        {
            "id": 3,
            "key": "bundle.alpha",
            "version": 1,
            "origin": "managed",
            "status": "ACTIVE",
            "type": "bundle",
            "displayName": "Bundle Alpha",
            "description": "Bundle description",
            "approvalMode": "not_required",
            "adapterKey": None,
            "configSchema": None,
            "bundleMembers": [
                {"memberType": "tool", "capabilityKey": "tool.alpha", "capabilityVersion": 1}
            ],
            "transport": None,
            "lifecycle": None,
            "createdAt": "2026-04-13T09:00:00Z",
            "updatedAt": "2026-04-13T09:30:00Z",
        }
    )

    assert runtime_create.inputs == {"ticker": "AAPL"}
    assert tryout_execute.agent_spec_key == "alpha_agent"
    assert workflow_read.entry_agent_key == "alpha_agent"
    assert workflow_read.model_dump(mode="json", by_alias=True)["mentionPolicy"] == {
        "version": 1,
        "allowCharacterPersonas": False,
        "allowedBuiltinHandles": ["librarian"],
    }
    assert capability_read.model_dump(mode="json", by_alias=True)["bundleMembers"] == [
        {"memberType": "tool", "capabilityKey": "tool.alpha", "capabilityVersion": 1}
    ]


def test_runtime_contracts_reject_invalid_shapes() -> None:
    with pytest.raises(ValidationError):
        TraceSummary.model_validate(
            {
                "eventCount": -1,
                "toolCallCount": 0,
                "warningCount": 0,
                "lastEventAt": None,
            }
        )

    with pytest.raises(ValidationError):
        ApprovalSummary.model_validate(
            {
                "totalCount": 1,
                "pendingCount": -1,
                "approvedCount": 0,
                "deniedCount": 0,
                "expiredCount": 0,
            }
        )

    with pytest.raises(ValidationError):
        PersonaProfileRef.model_validate({"personaProfileKey": "   "})

    with pytest.raises(ValidationError):
        CapabilityRef.model_validate({"capabilityKey": "", "capabilityVersion": 0})

    with pytest.raises(ValidationError):
        RuntimeRunCreate.model_validate(
            {
                "callerType": "api",
                "executionKind": "workflow",
                "agentSpecKey": "alpha_agent",
                "inputs": {},
            }
        )

    with pytest.raises(ValidationError):
        TryoutExecute.model_validate(
            {
                "workflowSpecKey": "alpha_workflow",
                "agentSpecKey": "alpha_agent",
                "inputs": {},
            }
        )
