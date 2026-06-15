# FRONTEND MEMORY PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/memory/` owns the platform Memory Admin browse/detail routes at `/memory` and `/memory/:memoryId`. The routes are a trusted local operator/admin control plane for canonical workflow memory across packages, backed by admin hooks in `use-memory.ts`, `api/memory.ts`, `types/memory.ts`, and route-local admin components/helpers.

Memory is platform-core ownership. It is not part of the Finance Workspace extension, and finance report history stays in Reports. Runtime `signaldeck.core.memory.lookup` and `signaldeck.core.memory.write` remain scoped to Workflow Package execution and must not become an unscoped global browser search path.

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
| Memory list route   | `list.tsx`                  | `/memory` admin workspace shell, URL-backed filters, create flow, linked list cards, and per-entry delete                  |
| Memory detail route | `detail.tsx`                | `/memory/:memoryId` workspace detail, tabs for detail/revisions/audit events, revise flow, workflow visibility update, and single-entry delete |
| Admin route UI      | `admin-components.tsx`      | Memory context bars, filters, list pane, cards, dialogs, tabs, JSON/detail/revision/event inspectors, and state panels     |
| Admin route helpers | `admin-helpers.ts`          | filter-param normalization, JSON parsing, operator provenance, subject refs, draft builders, and display formatting        |
| Memory hooks        | `../../hooks/use-memory.ts` | admin list/detail/history/create/revise/workflow-visibility/delete hooks plus separate scoped runtime memory hooks         |
| Memory API helpers  | `../../lib/api/memory.ts`   | admin `/api/memory/admin/entries*` helpers including single-entry delete plus scoped runtime `/api/memory` helpers         |
| Memory wire types   | `../../lib/types/memory.ts` | admin entries, scopes, `visibleToWorkflow`, provenance, history, write payloads, and separate runtime payloads            |
| Route metadata      | `../../routes.metadata.ts`  | platform-owned Memory Admin list/detail routes, Agent Platform sidebar item, scroll/wide shells, and admin state variants |

## CONVENTIONS

- `/memory` is the live browser list route and `/memory/:memoryId` is the live detail route for one memory entry.
- Selected memory is opened through real links to `/memory/:memoryId`; do not restore inline inspector or `memoryId` query-param selection.
- The page queries the trusted admin list immediately. Cross-package and mixed-scope rows are intended local operator visibility, not a package-private browser gate.
- Filters such as package, workflow, agent, run, scope, kind, `visibleToWorkflow`, and query narrow the operator-managed corpus; they do not authorize the corpus.
- Admin list default all-entry visibility is intentional. Hidden rows stay admin-visible, while only workflow-visible rows that match runtime scope and grant rules can affect future `signaldeck.core.memory.lookup`.
- Create, revise, workflow visibility, and single-entry delete controls must preserve explicit scope, `visibleToWorkflow`, operator provenance, immutable revision, and append-only history semantics where applicable.
- Shared namespace declarations and grants are not browser-authored here. Do not accept namespace declarations or grants from route JSON.
- The list route delegates Memory Admin filter/list/card/dialog UI to `admin-components.tsx` and helper normalization to `admin-helpers.ts`; keep data fetching and mutations in `list.tsx`/`detail.tsx` through hooks.
- The list route shows browse/filter results plus create and per-row single-entry delete controls; the detail route shows detail, revisions, events, provenance, revise, workflow visibility, and one-entry delete controls. It must not add bulk deletion, runtime/global delete behavior, browse report history, or promote report history into memory.
- `WorkspacePageShell` is the route frame for both list and detail; do not reintroduce a route-local page shell or inline inspector selection model.
- Keep Memory Admin in the Agent Platform nav group with platform ownership. Do not move it under extension gates or Finance Workspace ownership.
- Tool discovery stays API and hook support for Workflow Package capability authoring. Do not add or document a standalone Tools browser route from this folder.
- Long ids, memory content, subject refs, and event payload fragments need wrapping or internal scrolling so the route does not create mobile overflow.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add `/memory/:memoryId/revisions` or `/memory/:memoryId/events` child routes unless `src/routes.ts` and route metadata are intentionally changed.
- Do not call `api/memory.ts` directly from `list.tsx`, `detail.tsx`, or `admin-components.tsx`; use `use-memory.ts` so query keys and enabled gates stay centralized.
- Do not wire `/memory` back to scoped runtime `/api/memory` gating; use the admin hooks for the route and keep runtime helpers separate for Workflow Package execution paths.
- Do not treat opaque `memoryId` values as report slugs, download URLs, or routable finance identifiers.
- Do not add namespace wildcard search, vector activation/search, embeddings browser, chunk-table browser, grant-authoring UI, bulk delete, checkboxes, row selection, runtime/global delete actions, recycle bin, undo, tombstones, delete reasons, run/package ownership cascades, or report-history promotion to this route.
- Do not move Memory-specific dialog, draft, provenance, or JSON parsing behavior into `src/components/shared`; it is route-owned until another real route needs it.
- Do not duplicate Memory API types in the page. Add wire changes in `src/lib/types/memory.ts` and update hooks/API guides together.

## VALIDATION

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES

- `list.tsx` keeps URL-backed admin filter state, create mutation, delete mutation, and navigation local while delegating presentational pieces to `admin-components.tsx`.
- `detail.tsx` reads the route memory id and owns detail, revision, event, revise, workflow visibility, responsive action menu, and single-entry delete mutation wiring while runtime memory helpers remain separate.
- The route is intentionally a trusted local operator control plane, not a runtime global search surface.
