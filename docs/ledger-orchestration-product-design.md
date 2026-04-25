# Ledger Orchestration Product Design

## Status

This file is retained as a cutover reference only. The orchestration, Studio, Tryout, runtime-v2, agent-spec, workflow-spec, capability, and persona surfaces it originally described are retired and are not part of the shipped design.

## Current architecture

- `frontend/src/routes.ts` defines the flat route table for portfolios, templates, reports, and the agent-platform routes.
- `frontend/src/components/layout.tsx` owns the shell, breadcrumbs, and sidebar labels for the current shipped routes.
- `backend/app/main.py` mounts the preserved `/api/v1` router plus the current `/api/*` platform router.
- `backend/app/api/dependencies.py` wires the preserved product services and current agent-platform services.
- `backend/app/db/upgrades.py` creates current agent-platform tables, repairs stale agent-platform runs, and drops retired backend tables.

## Runtime model

The shipped runtime path is the stateless agent platform:
1. a saved workflow version is triggered through `/api/workflows/{id}/runs`
2. the backend persists the run row and executes the workflow in-process
3. run detail is exposed through `/api/runs/{id}` with per-step outputs and trace linkage
4. preserved portfolio, template, and report routes remain available beside the platform routes

## Design constraints

- keep retired orchestration, Studio, Tryout, runtime-v2, spec, capability, and persona surfaces out of current product docs
- keep preserved `/api/v1` product routes separate from the `/api/*` agent-platform routes
- keep the route and API docs aligned with the post-cutover code and cutover regression tests

## Evidence and grounding

- `frontend/src/routes.ts`
- `frontend/src/components/layout.tsx`
- `backend/app/main.py`
- `backend/app/api/router.py`
- `backend/app/api/platform_router.py`
- `backend/app/api/dependencies.py`
- `backend/app/db/upgrades.py`
- `backend/tests/test_legacy_backend_cutover.py`
