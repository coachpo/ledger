# RUN DETAIL SECTIONS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/pages/AGENTS.md`, and `/frontend/src/pages/runs/AGENTS.md`.

## OVERVIEW
`detail-sections/` owns the heavy run-detail presentation stack: tab workspaces, source-run rerun provenance, runtime capability/usage panes, and JSON payload panes. The parent `runs/detail.tsx` should orchestrate data, URL state, and layout; this folder renders the detailed evidence surfaces.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Section stack | `index.tsx` | tab workspaces, source-run rerun provenance, and inspection evidence |
| Runtime panes | `runtime.tsx`, `runtime-metadata.ts` | model gateway strategies, usage, resolved capabilities |
| Payload panes | `payload-sections.tsx` | input/output/final-output/JSON evidence blocks |
| Shared chrome | `shared.tsx`, `shared-helpers.ts` | detail section blocks, grids, empty states, status formatting |
| Export guard | `../detail-sections.exports.test.ts` | public export contract for route tests |

## CONVENTIONS
- `frontend/DESIGN.md` is the source of truth for status chrome, state panels, tokens, and management UI patterns inside the parent run-detail console.
- The parent `/runs/:runId` route is metadata `console` and must keep `WorkspacePageShell`; detail sections must not introduce nested page shells, route-local colored status badges, dashed empty states, or one-off `rounded-md border bg-muted/*` / `shadow-sm` page chrome.
- Keep `detail.tsx` as the route orchestrator; do not move route params, polling, or URL-state parsing here.
- Wide JSON, trace ids, and operation URLs must wrap or use internal scroll; do not create document-level horizontal overflow.
- Expensive evidence panes may use `content-visibility`/deferred section sizing as local presentation optimization.
- Shared helpers in this folder are route-detail helpers, not global UI primitives.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not flatten source-run provenance, runtime profiles, and payload JSON into one monolithic section.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/runs/detail-http-operations.test.tsx src/pages/runs/detail-sections.exports.test.ts
pnpm test:e2e -- runs.spec.ts
```
