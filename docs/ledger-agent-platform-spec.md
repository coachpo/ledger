# Ledger Agent Platform Functional Spec

> Status: Live functional spec as of 2026-05-04 (`b4ac445`).

## Scope

This document describes the shipped platform surface in this repository, not the retired orchestration, Studio, Tryout, runtime-v2, simulation, backtest, or skill-contract architecture.

## Shipped Routes

- Backend: `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/model-connections`, `/api/output-schemas`, `/api/workflows`, and `/api/runs`.
- Frontend: `/agents*`, `/capabilities*`, `/mcp-servers*`, `/model-connections*`, `/output-schemas*`, `/workflows*`, and `/runs*`.
- Preserved product routes remain under `/api/v1` and `/portfolios*`, `/templates*`, and `/reports*`.

## Resource Contracts

### Agents

- Agents are YAML-authored, versioned records with immutable historical versions.
- Manifests use `spec.capabilities`; `spec.skills` is rejected.
- Agents can reference output schemas, model settings, MCP servers, and capability refs.

### Capabilities

- Capabilities are canonical. They store tool grants as `toolGrants` and validate against the server-declared tool catalog.
### MCP Servers

- MCP servers are versioned resources with connection testing.
- Runtime execution uses enabled, exact-version pins and frozen tool snapshots.
- HTTP/SSE and stdio configs must stay inside the MCP security boundary.

### Model Connections

- Model connections store provider/base URL/default model/runtime settings and encrypted API keys.
- Reads and errors must mask or omit raw secrets.
- OpenAI-family base URLs are normalized and connection tests record last-test status.

### Output Schemas

- Output schemas use the locked supported schema subset.
- The backend validates and compiles runtime models before execution.

### Workflows And Runs

- Workflows are YAML-authored, versioned records with pinned refs and launch metadata.
- Launch creation accepts `{version, parameters}` and queues a persisted run.
- Runs expose status, inputs, per-step outputs, final output, timing, cost, trace ids, reruns, and step replays.

## Acceptance Baseline

- Agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs are authorable from current browser routes.
- Retired `/api/skills`, `/skills*`, Studio, Tryout, orchestration, simulation, backtest, and runtime-v2 routes are not part of the shipped contract.
