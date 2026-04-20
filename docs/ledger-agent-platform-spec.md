# Ledger Agent Platform — Functional Spec

## 1. Scope
Current shipped functional summary for Ledger's agent platform. This document describes the live platform surface in this repository, not an earlier target architecture.

## 2. Shipped surfaces
- Backend `/api/agents`, `/api/skills`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, and `/api/runs` routes.
- Frontend `/agents`, `/skills`, `/mcp-servers`, `/output-schemas`, `/workflows`, and `/runs` routes inside the main shell.
- Preserved `/api/v1` and frontend routes for portfolios, templates, and reports.
- No backward-compatibility layer for retired orchestration, Studio, Tryout, or runtime-v2 surfaces.

## 3. Resource contracts
### Agents
- Agents are versioned records with immutable historical versions.
- Each version stores explicit input schema, pinned output-schema version, pinned skill versions, pinned MCP server versions, model settings, and budget settings.
- The UI supports create, edit-as-new-version, duplicate, archive, and test-panel flows.

### Skills, MCP servers, and output schemas
- Skills, MCP servers, and output schemas are versioned resources with list/detail/editor flows.
- Skill tools are server-declared; the browser selects catalog entries rather than authoring executable tool code.
- MCP server auth is stored encrypted at rest.
- Output schemas support the repository's locked JSON Schema subset plus builder/JSON/preview editing in the UI.

### Workflows
- Workflows are versioned records with explicit input schema, ordered steps, slot names, per-field wiring, optional-agent flags, and a final output spec.
- Saving validates slot references, type compatibility, and pinned resource versions before a new workflow version is created.
- The shipped v1 model is linear and sequential across steps, with parallel agents inside each step.

### Runs
- `POST /api/workflows/{id}/runs` creates a persisted run row, returns immediately, and continues execution in the background.
- Run rows persist per-step and per-agent detail for the run monitor: resolved input, output or error payload, status, tokens, cost, duration, and trace-span metadata.
- Run list and detail routes expose current status, totals, final output, and trace linkage data when available.

## 4. Runtime behavior
- Runtime execution is service-owned and stateless between runs.
- Output schemas compile into runtime Pydantic models through the backend schema compiler.
- Budget enforcement applies both per-agent and across the full workflow.
- Startup repair marks leftover in-flight platform runs as failed after restart.

## 5. Observability and trace linkage
- Successful runs can persist a run-level `traceId` plus per-agent `traceSpanId` values in run detail.
- The shipped contract is trace-linkage metadata in the persisted run payload; this document does not require a specific external tracing product.

## 6. Acceptance baseline
- Agents, skills, MCP servers, output schemas, workflows, and runs are all authorable from the current browser UI.
- Retired orchestration, Studio, Tryout, and runtime-v2 routes are not part of the shipped contract.
- The stock-analysis reference workflow runs through the current platform surface and returns a typed `TradingDecision` payload.
