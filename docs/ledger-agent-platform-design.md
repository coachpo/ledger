# Ledger Agent Platform Technical Design

> Status: Live package-first technical design as of 2026-05-08.

## Overview

The shipped agent platform is a package-first backend/frontend surface layered into Ledger's existing FastAPI and React/Vite app. It persists Workflow Packages, global Model Connections, global read-only Tools metadata, and global Runs in PostgreSQL.

## Backend Shape

```text
backend/app/
  api/platform_router.py
  api/{workflow_packages,model_connections,tools,runs}.py
  services/{workflow_package,workflow_package_preflight,workflow_package_export,model_connection,run}_service.py
  services/workflow_package_manifest_{parser,compiler,decompiler}.py
  schemas/{workflow_package,workflow_package_manifest,model_connection,run}.py
  models/{workflow_package,model_connection,run,run_step,run_agent_invocation}.py
  repositories/{workflow_package,model_connection,run,run_step,run_agent_invocation}.py
  agents/{tool_catalog,runtime_tools,mcp}/
```

## Runtime Flow
1. A package launch reads launch metadata through `/api/workflow-packages/{packageId}/launch`.
2. The client posts `POST /api/workflow-packages/{packageId}/launches` with package version, workflow key, and parameters.
3. The backend validates the immutable package version, package-local resources, global tool keys, and live Model Connection keys.
4. Run execution uses official SDK-backed model clients through service-owned boundaries.
5. Native runtime tools and package-private MCP calls are dispatched only after package-local grant and security checks.
6. Per-step outputs, agent invocations, final output, totals, status, trace ids, package provenance, rerun metadata, and replay metadata are written to persisted run, step, and invocation rows.

## Security Boundaries

- Workflow Package exports omit secrets, encrypted credential payloads, database ids, and run history.
- Model Connection API keys remain encrypted at rest and secret-safe in reads/errors. Packages store Model Connection keys, not credentials.
- Tools are read-only server-declared metadata; packages reference tool keys but do not store global tool definitions.
- Private MCP config values stay inside package security boundaries, with required bindings and redacted/truncated output handling.
- Application LLM calls use official SDK clients rather than raw HTTP calls.

## Frontend Shape

- Platform API helpers live under `frontend/src/lib/api/`.
- Wire contracts live under `frontend/src/lib/types/`.
- Route pages live under `frontend/src/pages/{workflow-packages,model-connections,runs}/`.
- Query invalidation uses `frontend/src/lib/query-keys.ts` platform namespaces.

## Removed Route Notes

The old global authoring routes `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are absent after cutover. They are not compatibility aliases or redirects.

## Deployment

No additional service is required. Platform routes run inside the existing FastAPI app and use the same PostgreSQL database, CI, and GHCR Docker image flow as the rest of Ledger.
