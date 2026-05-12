# Ledger Agent Platform Reference

> Status: Live package-first platform reference for branch `main` at `10063aa`. This is the canonical platform reference.

## Scope

Ledger ships a package-first agent platform beside the preserved portfolio, template, and report product areas. Users author Workflow Packages, bind package agents to global Model Connections, reference read-only global Tools, launch package runs, and inspect persisted Runs from the browser.

This document describes shipped behavior only. Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, and retired legacy global authoring routes are not live surfaces.

## Live Surfaces

| Area | Backend | Frontend |
|---|---|---|
| Workflow Packages | `/api/workflow-packages*` | `/workflow-packages*` |
| Model Connections | `/api/model-connections*` | `/model-connections*` |
| Tools | `/api/tools` | surfaced inside package capability-profile editors |
| Runs | `/api/runs*` | `/runs*` |

Preserved product routes remain under `/api/v1` and `/portfolios*`, `/templates*`, and `/reports*`.

## Workflow Packages

Workflow Packages are the only live platform authoring root. Manifests use `ledger.workflowPackage/v1` YAML and store package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs inside immutable package versions.

Package-local refs use local keys. Model bindings use global Model Connection keys. Tool grants use global server-declared tool keys inside package-local capability profiles.

Package import/export is manifest based. Exports keep private MCP `env`, `headers`, and `query` values inline in the package text. This is an intentional breaking change, and the old binding-based private MCP contract no longer applies. Exports still omit database ids and run history.

## Model Connections

Model Connections are global live bindings for provider endpoint, model id, API style, reasoning effort, timeout defaults, encrypted API keys, status, and last connection-test metadata.

Read payloads and errors must mask or omit raw secrets. Blank API-key edits preserve the stored key; non-empty edits rotate it. Packages resolve Model Connections by key during validation, preflight, launch, and runtime.

## Tools

Tools are read-only server-declared metadata from `/api/tools`. Packages reference tool keys through local capability profiles; the platform does not expose global capability CRUD as a live route.

Current native tools cover market quote/history/OHLCV, indicators, fundamentals, news, insider data, positions, report lookup, and report memory writes. Runtime tool keys and OpenAI function names stay stable. Examples include `ledger.market_data.ohlcv_lookup`, `ledger.indicators.lookup`, `ledger.reports.lookup`, `ledger.reports.write`, and OpenAI function names such as `ledger_reports_lookup`.

## Runs

Package launch reads metadata from `GET /api/workflow-packages/{packageId}/launch`, then creates a run with `POST /api/workflow-packages/{packageId}/launches` using `{version, workflowKey, parameters}`.

Runs persist status, inputs, final output, token/timing totals, optional Logfire trace ids, per-invocation span ids, rerun metadata, step replay metadata, and package provenance. Detail payloads include steps and agent invocations for review without requiring a separate tracing product or Logfire token.

Run memory artifacts are memory-domain payloads. They expose `memoryId`, `summary`, `status`, `createdAt`, provenance, graph metadata when available, and optional `auditLinks.report` for report open/download actions while reports remain the backing store.

## UI Contract

`frontend/src/routes.ts` is the route source of truth. `frontend/src/components/layout.tsx` owns sidebar entries and breadcrumbs for Workflow Packages, Model Connections, and Runs.

List pages provide create/import actions, status/version badges, and archive/delete actions where supported. Editors use hooks and API modules rather than direct fetch calls from view code. Validation appears as inline alerts, field messages, toasts, and backend error-envelope messages.

Workflow Package and Template editor routes use the full-height layout region inside the normal shell.

## Backend Shape

```text
backend/app/api/platform_router.py
backend/app/api/{workflow_packages,model_connections,tools,runs}.py
backend/app/services/{workflow_package_service,workflow_package_preflight,workflow_package_export,run_service,model_connection_service}.py
backend/app/core/telemetry.py
backend/app/services/workflow_package_manifest_{parser,compiler,decompiler}.py
backend/app/schemas/{workflow_package,workflow_package_manifest,model_connection,run}.py
backend/app/models/{workflow_package,model_connection,run,run_step,run_agent_invocation}.py
```

## Frontend Shape

```text
frontend/src/routes.ts
frontend/src/components/layout.tsx
frontend/src/pages/{workflow-packages,model-connections,runs}/
frontend/src/hooks/{use-workflow-packages,use-model-connections,use-runs}.ts
frontend/src/lib/api/{workflow-packages,model-connections,tools,runs}.ts
frontend/src/lib/types/{workflow-package,model-connection,tool,run}.ts
frontend/src/lib/platform-authoring/**
```

## Retired Surfaces

The retired legacy global authoring routes `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are absent from the mounted app and the live router. They are not compatibility aliases or redirects.

Legacy/unmounted backend modules may still exist for cutover regression context, but current docs must not present them as live routes. Current guardrails live in `backend/tests/test_legacy_backend_cutover.py`, `backend/tests/test_workflow_package_openapi.py`, `frontend/src/routes.test.tsx`, and `frontend/src/platform-clean-break.test.ts`.

## Validation

```bash
(cd backend && uv run pytest tests/test_workflow_package_openapi.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_workflow_package_runtime_artifacts.py)
(cd frontend && pnpm test:run src/routes.test.tsx src/pages/workflow-packages/preflight-launch-export.test.tsx src/pages/workflow-packages/resource-editors.test.tsx)
```
