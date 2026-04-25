# Ledger Orchestration Product PRD

## Status

This file is retained as a cutover reference only. The orchestration, Studio, Tryout, runtime-v2, agent-spec, workflow-spec, capability, and persona surfaces it originally described are retired and are not part of the shipped product.

## Current product summary

Ledger now ships a stateless agent platform alongside the preserved portfolio, template, and report product areas. Users create agents, skills, MCP servers, output schemas, and workflows in the browser, then trigger and inspect runs from the routed workspace.

## Current scope

The shipped browser-facing surface includes:
- portfolio list/detail routes
- template list/editor routes
- report list/detail routes
- agents, skills, MCP servers, output schemas, workflows, and runs routes
- backend `/api/v1` preserved-product routes plus `/api/*` agent-platform routes

## Non-goals

- no backward compatibility promise for retired orchestration or runtime-v2 browser/API surfaces
- no claim that Studio, Tryout, or orchestration routes remain part of the current product
- no claim that retired spec, capability, or persona catalogs are still user-facing surfaces

## Evidence and grounding

- `frontend/src/routes.ts`
- `frontend/src/components/layout.tsx`
- `backend/app/main.py`
- `backend/app/api/router.py`
- `backend/app/api/platform_router.py`
- `backend/tests/test_legacy_backend_cutover.py`

## Success criteria

- docs describe the preserved `/api/v1` product routes and the current `/api/*` agent-platform routes truthfully
- docs do not present retired orchestration, Studio, Tryout, runtime-v2, spec, capability, or persona surfaces as current
