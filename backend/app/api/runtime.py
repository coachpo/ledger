from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_agent_runtime_service, get_studio_query_service
from app.schemas.runtime import (
    RuntimeApprovalActionRead,
    RuntimeApprovalActionRequest,
    RuntimeApprovalListRead,
    RuntimeApprovalRead,
    RuntimeApprovalStatus,
    RuntimeArtifactRead,
    RuntimeCallerType,
    RuntimeCancelRead,
    RuntimeRunCreate,
    RuntimeRunCreated,
    RuntimeRunListRead,
    RuntimeRunRead,
    RuntimeTraceEventListRead,
    RuntimeTraceEventType,
)
from app.services.agent_runtime_service import AgentRuntimeService
from app.services.studio_query_service import StudioQueryService

router = APIRouter(prefix="/runtime", tags=["runtime"])


@router.get("/runs", response_model=RuntimeRunListRead)
def list_runtime_runs(
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
    caller_type: Annotated[RuntimeCallerType | None, Query(alias="callerType")] = None,
    caller_id: Annotated[int | None, Query(alias="callerId")] = None,
    caller_scope_key: Annotated[str | None, Query(alias="callerScopeKey")] = None,
    caller_identity_key: Annotated[str | None, Query(alias="callerIdentityKey")] = None,
    workflow_spec_key: Annotated[str | None, Query(alias="workflowSpecKey")] = None,
) -> RuntimeRunListRead:
    return service.list_runs(
        caller_type=caller_type,
        caller_id=caller_id,
        caller_scope_key=caller_scope_key,
        caller_identity_key=caller_identity_key,
        workflow_spec_key=workflow_spec_key,
    )


@router.post("/runs", response_model=RuntimeRunCreated, status_code=status.HTTP_201_CREATED)
def create_runtime_run(
    payload: RuntimeRunCreate,
    service: Annotated[AgentRuntimeService, Depends(get_agent_runtime_service)],
) -> RuntimeRunCreated:
    return service.create_public_run(payload)


@router.get("/runs/{run_id}", response_model=RuntimeRunRead)
def get_runtime_run(
    run_id: int,
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
) -> RuntimeRunRead:
    return service.get_run(run_id)


@router.get("/runs/{run_id}/artifacts", response_model=RuntimeArtifactRead)
def get_runtime_artifact(
    run_id: int,
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
) -> RuntimeArtifactRead:
    return service.get_artifact(run_id)


@router.get("/runs/{run_id}/trace", response_model=RuntimeTraceEventListRead)
def get_runtime_run_trace(
    run_id: int,
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
) -> RuntimeTraceEventListRead:
    return service.list_run_trace(run_id)


@router.post("/runs/{run_id}/cancel", response_model=RuntimeCancelRead)
def cancel_runtime_run(
    run_id: int,
    service: Annotated[AgentRuntimeService, Depends(get_agent_runtime_service)],
) -> RuntimeCancelRead:
    return service.cancel_run(run_id)


@router.get("/approvals", response_model=RuntimeApprovalListRead)
def list_runtime_approvals(
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
    run_id: Annotated[int | None, Query(alias="runId")] = None,
    caller_type: Annotated[RuntimeCallerType | None, Query(alias="callerType")] = None,
    caller_id: Annotated[int | None, Query(alias="callerId")] = None,
    workflow_spec_key: Annotated[str | None, Query(alias="workflowSpecKey")] = None,
    capability_key: Annotated[str | None, Query(alias="capabilityKey")] = None,
    approval_status: Annotated[RuntimeApprovalStatus | None, Query(alias="status")] = None,
) -> RuntimeApprovalListRead:
    return service.list_approvals(
        run_id=run_id,
        caller_type=caller_type,
        caller_id=caller_id,
        workflow_spec_key=workflow_spec_key,
        capability_key=capability_key,
        status=approval_status,
    )


@router.get("/approvals/{approval_id}", response_model=RuntimeApprovalRead)
def get_runtime_approval(
    approval_id: int,
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
) -> RuntimeApprovalRead:
    return service.get_approval(approval_id)


@router.get("/trace-events", response_model=RuntimeTraceEventListRead)
def list_runtime_trace_events(
    service: Annotated[StudioQueryService, Depends(get_studio_query_service)],
    run_id: Annotated[int | None, Query(alias="runId")] = None,
    caller_type: Annotated[RuntimeCallerType | None, Query(alias="callerType")] = None,
    caller_id: Annotated[int | None, Query(alias="callerId")] = None,
    workflow_spec_key: Annotated[str | None, Query(alias="workflowSpecKey")] = None,
    capability_key: Annotated[str | None, Query(alias="capabilityKey")] = None,
    event_type: Annotated[RuntimeTraceEventType | None, Query(alias="eventType")] = None,
) -> RuntimeTraceEventListRead:
    return service.list_trace_events(
        run_id=run_id,
        caller_type=caller_type,
        caller_id=caller_id,
        workflow_spec_key=workflow_spec_key,
        capability_key=capability_key,
        event_type=event_type,
    )


@router.post("/approvals/{approval_id}/approve", response_model=RuntimeApprovalActionRead)
def approve_runtime_approval(
    approval_id: int,
    payload: RuntimeApprovalActionRequest,
    service: Annotated[AgentRuntimeService, Depends(get_agent_runtime_service)],
) -> RuntimeApprovalActionRead:
    return service.approve_approval(
        approval_id,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.post("/approvals/{approval_id}/deny", response_model=RuntimeApprovalActionRead)
def deny_runtime_approval(
    approval_id: int,
    payload: RuntimeApprovalActionRequest,
    service: Annotated[AgentRuntimeService, Depends(get_agent_runtime_service)],
) -> RuntimeApprovalActionRead:
    return service.deny_approval(
        approval_id,
        actor=payload.actor,
        reason=payload.reason,
    )
