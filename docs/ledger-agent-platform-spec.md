# Ledger Agent Platform Functional Spec

> Status: Live package-first functional spec as of 2026-05-08.

## Scope

This document describes the shipped package-first platform surface in this repository, not the retired orchestration, Studio, Tryout, runtime-v2, simulation, backtest, skill-contract, or old global authoring architecture.

## Shipped Routes

- Backend: `/api/workflow-packages`, `/api/model-connections`, `/api/tools`, and `/api/runs`.
- Frontend: `/workflow-packages*`, `/model-connections*`, and `/runs*`.
- Preserved product routes remain under `/api/v1` and `/portfolios*`, `/templates*`, and `/reports*`.
- Removed route notes: `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are absent and must not be documented as live aliases.

## Resource Contracts

### Workflow Packages
- Workflow Packages are YAML-authored, versioned records with immutable historical versions.
- Manifests use `ledger.workflowPackage/v1` and keep agents, output schemas, capability profiles, private MCP configs, and workflow graphs package-private.
- Package-local refs use local keys. Model bindings use global Model Connection keys. Tool grants use global server-declared tool keys inside package-local capability profiles.
- Package exports omit secrets, encrypted credential payloads, database ids, and run history.

### Model Connections

- Model Connections store provider/base URL/default model/runtime settings and encrypted API keys as global live bindings.
- Reads and errors must mask or omit raw secrets.
- Packages resolve Model Connections by key at validation, preflight, launch, and runtime without copying provider credentials.

### Tools

- Tools are read-only server-declared metadata exposed through `/api/tools`.
- Packages reference tool keys through local capability profiles; the platform does not expose global capability CRUD.

### Runs

- Launch creation accepts package version, workflow key, and parameters, then queues a persisted global run.
- Runs expose status, inputs, package provenance, per-step outputs, agent invocations, final output, timing, token usage, trace ids, reruns, and step replays.
## Acceptance Baseline

- Workflow Packages, Model Connections, and Runs are reachable from current browser routes.
- `/api/tools` exposes global read-only tool metadata.
- Package imports and exports are no-secret, no-database-id YAML operations.
- Runs store immutable package id, key, version, hash, workflow key, local resource refs, and no-secret launch snapshots.
- Retired `/api/skills`, `/skills*`, Studio, Tryout, orchestration, simulation, backtest, runtime-v2 routes, and old global authoring routes are rejected or absent, not hidden live routes.
