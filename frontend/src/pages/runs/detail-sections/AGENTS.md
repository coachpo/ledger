# RUN DETAIL SECTIONS GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, `/frontend/src/pages/AGENTS.md`, and `/frontend/src/pages/runs/AGENTS.md`.

## OVERVIEW
`detail-sections/` owns the heavy run-detail presentation stack: tab workspaces, lineage diagrams, memory evidence groups, runtime capability/usage panes, JSON payload panes, and the invocation-specific fork dialog. The parent `runs/detail.tsx` should orchestrate data, URL state, and layout; this folder renders the detailed evidence surfaces.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Section stack | `index.tsx` | tab workspaces, lineage graph, memory groups, inspection evidence |
| Fork dialog | `fork-dialog.tsx` | invocation-input fork draft/load/edit/create flow |
| Runtime panes | `runtime.tsx`, `runtime-metadata.ts` | model gateway strategies, usage, resolved capabilities |
| Payload panes | `payload-sections.tsx` | input/output/final-output/JSON evidence blocks |
| Shared chrome | `shared.tsx`, `shared-helpers.ts` | detail section blocks, grids, empty states, status formatting |
| Export guard | `../detail-sections.exports.test.ts` | public export contract for route tests |

## CONVENTIONS
- Keep `detail.tsx` as the route orchestrator; do not move route params, polling, or URL-state parsing here.
- Keep the fork dialog invocation-specific. It edits full replacement `invocationInput` for one source invocation and leaves root parameters to rerun.
- Treat `memoryId` as opaque. Human audit report links come only from `artifact.auditLinks.report`, never from derived memory identifiers.
- Wide JSON, trace ids, lineage nodes, and operation URLs must wrap or use internal scroll; do not create document-level horizontal overflow.
- Expensive evidence panes may use `content-visibility`/deferred section sizing as local presentation optimization.
- Shared helpers in this folder are route-detail helpers, not global UI primitives.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not flatten memory events, lineage evidence, runtime profiles, and payload JSON into one monolithic section.
- Do not use `resumeStepIndex` alone as an editable fork target; invocation id is required.
- Do not expose operation/tool invocation forks as live actions in phase 1.
- Do not bypass `use-runs.ts` hooks for fork draft/create behavior.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/runs/detail.test.tsx src/pages/runs/detail-http-operations.test.tsx src/pages/runs/detail-sections.exports.test.ts
```
