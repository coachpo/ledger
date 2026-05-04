# Ledger Agent Platform Migration And Deletion Plan

> Status: Live cutover-state reference as of 2026-05-04 (`b4ac445`).

## Current Shipped State

The cutover is complete. Ledger now ships:

- preserved `/api/v1` routes for portfolios, balances, positions, trading operations, market data, templates, and reports
- current `/api/*` routes for agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs
- frontend routes for portfolios, templates, reports, and the current agent-platform surfaces

There is no backward-compatibility layer for retired `/api/skills`, `/skills*`, orchestration, Studio, Tryout, runtime-v2, simulation, or backtest browser/API surfaces.

## Shipped Backend Authority

- `backend/app/db/session.py` owns startup initialization.
- `backend/app/db/upgrades.py` owns additive current-platform table creation, stale-run repair, and retired-table cleanup.
- `backend/alembic/` is scaffolding only and is not the migration source of truth.

## Shipped Platform Persistence

Versioned platform resources persist in `agents`, `capabilities`, `mcp_servers`, `model_connections`, `output_schemas`, `workflows`, and `runs` tables.
These resources use numeric primary keys, stable logical keys where applicable, immutable versions for versioned resources, archive flags instead of hard deletion where needed, and persisted run detail sufficient for UI inspection.

## Cleanup Notes

- Retired route families should remain absent from `frontend/src/routes.ts` and backend routers.
- Retired terms such as skill contracts may appear only as explicit rejected legacy input, not as current product surfaces.
- Future cleanup should stay aligned with `backend/app/db/upgrades.py`, current route mounts, and cutover regression tests.
