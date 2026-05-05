# Ledger Agent Platform Technical Design

> Status: Live technical design as of 2026-05-05 (`a8ad8fb`).

## Overview

The shipped agent platform is a stateless backend/frontend surface layered into Ledger's existing FastAPI and React/Vite app. It persists agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs in PostgreSQL.

## Backend Shape

```text
backend/app/
  api/platform_router.py
  api/{agents,capabilities,mcp_servers,model_connections,output_schemas,workflows,runs}.py
  services/{agent,capability,mcp_server,model_connection,output_schema,workflow,run}_service.py
  schemas/{agent,capability,mcp_server,model_connection,output_schema,workflow,run}.py
  models/{agent,capability,mcp_server,model_connection,output_schema,workflow,run,run_step,run_agent_invocation}.py
  repositories/{agent,capability,mcp_server,model_connection,output_schema,workflow,run,run_step,run_agent_invocation}.py
  agents/{tool_catalog,runtime_tools,mcp}/
```

## Runtime Flow

1. A workflow launch reads launch metadata through `/api/workflows/{workflowId}/launch`.
2. The client posts `POST /api/workflows/{workflowId}/launches` with `{version, parameters}`.
3. The backend validates the pinned workflow, agents, capabilities, MCP servers, model connections, and output schemas.
4. Run execution uses official SDK-backed model clients through service-owned boundaries.
5. Native runtime tools and MCP calls are dispatched only after grant checks.
6. Per-step outputs, agent invocations, final output, totals, status, trace ids, rerun metadata, and replay metadata are written to persisted run, step, and invocation rows.

## Security Boundaries

- Capabilities are the only live tool-key contract; `spec.skills` is rejected.
- MCP URL, stdio, redirect, exact-pin, frozen snapshot, schema-hash, and output redaction/truncation checks are runtime boundaries.
- Model-connection API keys remain encrypted at rest and secret-safe in reads/errors.
- Application LLM calls use official SDK clients rather than raw HTTP calls.

## Frontend Shape

- Platform API helpers live under `frontend/src/lib/api/`.
- Wire contracts live under `frontend/src/lib/types/`.
- Route pages live under `frontend/src/pages/{agents,capabilities,mcp-servers,model-connections,output-schemas,workflows,runs}/`.
- Query invalidation uses `frontend/src/lib/query-keys.ts` platform namespaces.

## Deployment

No additional service is required. Platform routes run inside the existing FastAPI app and use the same PostgreSQL database, CI, and GHCR Docker image flow as the rest of Ledger.
