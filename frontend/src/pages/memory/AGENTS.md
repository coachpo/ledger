# FRONTEND MEMORY PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/memory/` owns the single platform Memory route at `/memory`. The route is a trusted local operator/admin control plane for canonical workflow memory across packages, backed by admin hooks in `use-memory.ts`, `api/memory.ts`, and `types/memory.ts`.

Memory is platform-core ownership. It is not part of the Finance Workspace extension, and finance report history stays in Reports. Runtime `signaldeck.memory.lookup/write` remains scoped to Workflow Package execution and must not become an unscoped global browser search path.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Memory route | `list.tsx` | `/memory` admin inventory, optional filters, create/revise/status flows, list cards, and inline detail panes |
| Memory hooks | `../../hooks/use-memory.ts` | admin list/detail/history/create/revise/status hooks plus separate scoped runtime memory hooks |
| Memory API helpers | `../../lib/api/memory.ts` | admin `/api/memory/admin/entries*` helpers plus scoped runtime `/api/memory` helpers |
| Memory wire types | `../../lib/types/memory.ts` | admin entries, scopes, status, provenance, history, write payloads, and separate runtime payloads |
| Route metadata | `../../routes.metadata.ts` | platform-owned Memory Admin route, Agent Platform sidebar item, full-height shell, and admin state variants |

## CONVENTIONS

- `/memory` is the only live browser route for this folder. There is no `/memory/:memoryId` route today.
- Selected memory is opened inline through the `memoryId` search param, not by routing to a detail page.
- The page queries the trusted admin list immediately. Cross-package and mixed-scope rows are intended local operator visibility, not a package-private browser gate.
- Filters such as package, workflow, agent, run, scope, kind, status, and query narrow the operator-managed corpus; they do not authorize the corpus.
- Admin list default all-status visibility is intentional. Pending and expired rows stay admin-visible, while only resolved rows that match runtime scope and grant rules can affect future `signaldeck.memory.lookup`.
- Create, revise, and status controls must preserve explicit scope, lifecycle status, operator provenance, immutable revision, and append-only history semantics.
- Shared namespace declarations and grants are not browser-authored here. Do not accept namespace declarations or grants from route JSON.
- The route can show list results plus inline detail, revisions, events, provenance, and write/status controls. It must not add destructive delete actions, browse report history, or promote report history into memory.
- Keep Memory Admin in the Agent Platform nav group with platform ownership. Do not move it under extension gates or Finance Workspace ownership.
- Tool discovery stays API and hook support for Workflow Package capability authoring. Do not add or document a standalone Tools browser route from this folder.
- Long ids, memory content, subject refs, and event payload fragments need wrapping or internal scrolling so the route does not create mobile overflow.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add `/memory/:memoryId`, `/memory/:memoryId/revisions`, or `/memory/:memoryId/events` routes unless `src/routes.ts` and route metadata are intentionally changed.
- Do not call `api/memory.ts` directly from `list.tsx`; use `use-memory.ts` so query keys and enabled gates stay centralized.
- Do not wire `/memory` back to scoped runtime `/api/memory` gating; use the admin hooks for the route and keep runtime helpers separate for Workflow Package execution paths.
- Do not treat opaque `memoryId` values as report slugs, download URLs, or routable finance identifiers.
- Do not add namespace wildcard search, vector activation/search, embeddings, chunk tables, grant-authoring UI, destructive delete actions, or report-history promotion to this route.
- Do not duplicate Memory API types in the page. Add wire changes in `src/lib/types/memory.ts` and update hooks/API guides together.

## VALIDATION

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES

- `list.tsx` keeps admin filter and write-dialog draft state local to the page.
- Admin detail, revision, and event reads use the selected memory id plus the admin API, while runtime memory helpers remain separate.
- The route is intentionally a trusted local operator control plane, not a runtime global search surface.
