# Ledger Agent Platform — Migration & Deletion Plan

## 1. Current shipped state
The migration is complete. Ledger now ships:
- preserved `/api/v1` routes for portfolios, balances, positions, trading, market data, templates, and reports
- current `/api/*` routes for agents, skills, MCP servers, output schemas, workflows, and runs
- frontend routes for portfolios, templates, reports, and the agent-platform surfaces

There is no backward-compatibility layer for the retired orchestration, Studio, Tryout, or runtime-v2 browser and API surfaces.

## 2. Retired surfaces
The cutover removed the old orchestration and runtime stack from shipped product paths. The retired backend and frontend modules remain only as historical cutover context and destructive-cleanup coverage.

Representative cutover guarantees live in:
- `backend/tests/test_legacy_backend_cutover.py`
- `backend/app/api/router.py`
- `backend/app/api/platform_router.py`
- `frontend/src/routes.ts`

## 3. Shipped backend authority
The current repository uses `backend/app/db/` as the schema authority.
- `backend/app/db/session.py` owns startup initialization
- `backend/app/db/upgrades.py` owns additive platform-table creation, stale-run recovery, and retired-table cleanup
- `backend/alembic/` is scaffolding only and is not the migration source of truth

## 4. Shipped platform persistence
The current platform persists versioned rows for:
- `agents`
- `skills`
- `mcp_servers`
- `output_schemas`
- `workflows`
- `runs`

These tables use numeric primary keys plus stable `key` fields and immutable integer `version` fields for the versioned resources. Run rows persist pinned workflow identity, per-step outputs, totals, status, timestamps, and optional trace ids.

## 5. Cleanup notes
Retired orchestration, tryout, and runtime-v2 code paths were removed from shipped routes and are no longer part of the active product. Any further cleanup should stay aligned with the `app/db/` upgrade path and the current route mounts.
