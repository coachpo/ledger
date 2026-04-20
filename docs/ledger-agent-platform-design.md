# Ledger Agent Platform — Technical Design

## 1. Overview
The shipped Ledger agent platform is a stateless backend and frontend surface layered into the existing repository. Agents, skills, MCP servers, output schemas, workflows, and runs are persisted in PostgreSQL and exposed through the current `/api/*` routes, alongside the preserved portfolio, template, and report product areas.

The live backend uses the existing `app/*` layers:
- `app/api/` for route handlers
- `app/services/` for versioned CRUD, validation, and run execution
- `app/models/` and `app/repositories/` for persistence
- `app/db/` for startup-owned schema repair and legacy-table cleanup

## 2. Current backend shape
```text
backend/app/
  api/
    router.py             # preserved /api/v1 routes
    platform_router.py    # current /api/* platform routes
    agents.py
    skills.py
    mcp_servers.py
    output_schemas.py
    workflows.py
    runs.py
  services/
    agent_service.py
    skill_service.py
    mcp_server_service.py
    output_schema_service.py
    workflow_service.py
    run_service.py
  models/
  repositories/
  schemas/
  db/
```

## 3. Data model
The shipped implementation stores versioned records for agents, skills, MCP servers, output schemas, workflows, and runs. These tables use numeric primary keys plus stable `key` fields and immutable integer `version` fields for versioned resources. Agent rows keep model settings, prompts, linked skills, linked MCP servers, and output schema references. Workflow rows keep input, step, and output configuration. Run rows keep execution input, per-step outputs, final output, status, optional `trace_id`, totals, and timestamps.

## 4. Runtime flow
1. `POST /api/workflows/{id}/runs` validates input against the workflow schema.
2. The backend loads the pinned workflow version and the referenced agent and schema records.
3. Each step resolves its inputs from the initial request or prior step outputs.
4. The backend executes the configured agents, collects outputs, and writes them into the run record.
5. The final output is resolved from the workflow output configuration and returned.

## 5. Runtime integration
Agent construction happens in the backend service layer from stored configuration. Skills and MCP servers are resolved from the configured backend records. Runs persist execution metadata with each workflow invocation and store a `trace_id` when tracing is available; the platform remains usable when tracing is unavailable.

## 6. Error model
- Input validation errors return 400 with field level messages.
- Save time schema errors return 422.
- Runtime failures mark the run failed and store the error.

## 7. Deployment
- No new service, runs inside the existing FastAPI app.
- Database schema repair and upgrade paths live in `app/db/`.
- Deployment follows the existing backend startup path.
