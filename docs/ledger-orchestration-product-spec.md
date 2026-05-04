# Ledger Orchestration Product Spec

## Status

This document is retained as a cutover reference only. The orchestration, Studio, Tryout, runtime-v2, agent-spec, workflow-spec, capability, and persona surfaces it originally described are retired and are not part of the shipped product.

## Current shipped surface

Frontend routes from `frontend/src/routes.ts`:
- `/portfolios`
- `/portfolios/:portfolioId`
- `/templates`
- `/templates/new`
- `/templates/:templateId/edit`
- `/reports`
- `/reports/:slug`
- `/agents`
- `/agents/new`
- `/agents/:agentId/edit`
- `/capabilities`
- `/capabilities/new`
- `/capabilities/:capabilityId/edit`
- `/mcp-servers`
- `/mcp-servers/new`
- `/mcp-servers/:serverId/edit`
- `/output-schemas`
- `/output-schemas/new`
- `/output-schemas/:schemaId/edit`
- `/workflows`
- `/workflows/new`
- `/workflows/:workflowId`
- `/workflows/:workflowId/edit`
- `/workflows/:workflowId/run`
- `/runs`
- `/runs/:runId`

Backend API routes:
- `/api/v1` for portfolios, balances, positions, trading operations, market data, templates, and reports
- `/api/agents`
- `/api/capabilities`
- `/api/mcp-servers`
- `/api/output-schemas`
- `/api/workflows`
- `/api/workflows/{workflowId}/launch`
- `/api/workflows/{workflowId}/versions`
- `/api/workflows/{workflowId}/launches`
- `/api/runs`
- `/api/runs/{runId}/rerun-draft`
- `/api/runs/{runId}/reruns`
- `/api/runs/{runId}/step-replay-draft`
- `/api/runs/{runId}/step-replays`

## Response and compatibility notes

- JSON is camelCase externally.
- Capabilities are canonical. `/api/capabilities` emits `toolGrants`; `/api/skills` and `toolDefinitions` are retired and unsupported.
- Frontend `/capabilities*` routes are canonical. `/skills*` routes are retired and unsupported.
- Manifests use `spec.capabilities`; `spec.skills` is retired and rejected.
- Runtime tool keys and OpenAI function names stay unchanged.
- Workflow launches use the strict `{version, parameters}` request envelope and create queued runs.
- Runs expose typed input, per-step outputs, final output, status, timing, and trace identifiers through the current run schemas.
- Reruns and step replays replace the retired fork terminology in live API and UI docs.
- Retired `/api/v1/orchestration/*` and `/api/v2/*` surfaces are not part of the current contract and should not be treated as live documentation targets.

## Evidence and grounding

- `frontend/src/routes.ts`
- `frontend/src/components/layout.tsx`
- `backend/app/main.py`
- `backend/app/api/router.py`
- `backend/app/api/platform_router.py`
- `backend/app/api/dependencies.py`
- `backend/app/db/upgrades.py`
- `backend/tests/test_legacy_backend_cutover.py`
