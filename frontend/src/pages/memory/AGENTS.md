# FRONTEND MEMORY PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/memory/` owns the workflow memory review route at `/memory`. The route is a trusted local operator review surface for proposals, audit events, and quarantine evidence, backed by review hooks in `use-memory.ts`, `api/memory.ts`, `types/memory.ts`, and route-local components/helpers.

Memory is platform-core ownership. It is not part of the Finance Workspace extension, and finance report history stays in Reports. Workflow Package `spec.memory` middleware and review APIs remain scoped to package execution and must not become an unscoped global browser search path.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task                | Location                    | Notes                                                                                                                     |
| ------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Memory review route | `list.tsx`                  | `/memory` review workspace with proposal, audit-event, and quarantine tabs plus approve/reject actions                    |
| Memory hooks        | `../../hooks/use-memory.ts` | proposal list, approve/reject, audit-event list, and quarantine list hooks                                                |
| Memory API helpers  | `../../lib/api/memory.ts`   | `/api/memory/proposals`, `/api/memory/audit-events`, and `/api/memory/quarantine` helpers plus proposal decisions         |
| Memory wire types   | `../../lib/types/memory.ts` | proposal, decision, audit-event, and quarantine payloads                                                                 |
| Route metadata      | `../../routes.metadata.ts`  | platform-owned workflow memory review route, Agent Platform sidebar item, scroll/wide shell, and review state variants    |

## CONVENTIONS

- `/memory` is the live browser route for workflow memory proposal review, audit events, and quarantine evidence.
- The page queries review endpoints only. Cross-package review visibility is intended local operator visibility, not a package-private browser gate.
- Review filters narrow proposal, audit, and quarantine lists for operator triage; they do not authorize workflow memory retrieval.
- Approve and reject controls must preserve explicit operator decisions and policy provenance. Policy service activation remains the only path from accepted proposal to committed workflow memory.
- Shared namespace declarations and grants are not browser-authored here. Do not accept namespace declarations or grants from route JSON.
- The route keeps review data fetching and proposal decisions in `list.tsx` through hooks.
- The route shows proposal, audit-event, and quarantine evidence only. It must not add memory CRUD, global search, report-history browsing, or report-history promotion to workflow memory.
- `WorkspacePageShell` is the route frame; do not reintroduce detail pages, route-local page shells, or inline inspector selection models.
- Route metadata includes list loading/error/empty/review states; keep proposal decision feedback in route-owned states rather than generic shared shell state.
- Keep workflow memory review in the Agent Platform nav group with platform ownership. Do not move it under extension gates or Finance Workspace ownership.
- Tool discovery stays API and hook support for Workflow Package capability authoring. Do not add or document a standalone Tools browser route from this folder.
- Long ids, memory content, subject refs, and event payload fragments need wrapping or internal scrolling so the route does not create mobile overflow.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add memory detail, revision, event, or entry CRUD child routes.
- Do not call `api/memory.ts` directly from `list.tsx`; use `use-memory.ts` so query keys and enabled gates stay centralized.
- Do not wire `/memory` to model-execution memory paths; use only proposal, audit-event, quarantine, approve, and reject helpers.
- Do not treat opaque `memoryId` values as report slugs, download URLs, or routable finance identifiers.
- Do not add namespace wildcard search, vector activation/search, embeddings browser, chunk-table browser, grant-authoring UI, bulk delete, checkboxes, row selection, global delete actions, recycle bin, undo, tombstones, delete reasons, run/package ownership cascades, or report-history promotion to this route.
- Do not move Memory-specific review, decision, provenance, or JSON parsing behavior into `src/components/shared`; it is route-owned until another real route needs it.
- Do not duplicate Memory API types in the page. Add wire changes in `src/lib/types/memory.ts` and update hooks/API guides together.

## VALIDATION

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES

- `list.tsx` keeps review tab state, proposal approve/reject mutations, and list rendering local.
- The route is intentionally a trusted local operator review surface, not a global search or storage surface.
