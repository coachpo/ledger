# FRONTEND MEMORY PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/memory/` owns the single platform Memory route at `/memory`. The route is an Agent Platform inventory surface for canonical memory reads through `/api/memory`, backed by `use-memory.ts`, `api/memory.ts`, and `types/memory.ts`.

Memory is platform-core ownership. It is not part of the Finance Workspace extension, and finance report history stays in Reports.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

## WHERE TO LOOK

| Task | Location | Notes |
|---|---|---|
| Memory route | `list.tsx` | `/memory` inventory, access-context form, scoped filters, list cards, and inline detail panes |
| Memory hooks | `../../hooks/use-memory.ts` | list, detail, revisions, and events queries with caller-owned `enabled` gating |
| Memory API helpers | `../../lib/api/memory.ts` | POST read helpers for `/api/memory`, `/api/memory/{memoryId}/detail`, revisions, and events |
| Memory wire types | `../../lib/types/memory.ts` | access context, scopes, list/detail, revision, and event payloads |
| Route metadata | `../../routes.metadata.ts` | platform-owned inventory route, Agent Platform sidebar item, scroll shell, and state variants |

## CONVENTIONS

- `/memory` is the only live browser route for this folder. There is no `/memory/:memoryId` route today.
- Selected memory is opened inline through the `memoryId` search param, not by routing to a detail page.
- The page must require an explicit package access context before calling `/api/memory`.
- Reads must also require a concrete private scope: run, package, workflow, or agent.
- Shared namespace grants are not browser-authored here. Do not accept namespace declarations or grants from route JSON.
- Keep `visibility: "explicit-scope"` aligned with the backend memory contract.
- The route can show list results plus inline detail, revisions, and events panes. It must not create, edit, delete, or browse report history.
- Access-denied responses should stay distinct from generic load failures because the backend is enforcing package and scope authorization.
- Keep Memory in the Agent Platform nav group with platform ownership. Do not move it under extension gates or Finance Workspace ownership.
- Tool discovery stays API and hook support for Workflow Package capability authoring. Do not add or document a standalone Tools browser route from this folder.
- Long ids, memory content, subject refs, and event payload fragments need wrapping or internal scrolling so the route does not create mobile overflow.

## ANTI-PATTERNS

- Do not add `/memory/:memoryId`, `/memory/:memoryId/revisions`, or `/memory/:memoryId/events` routes unless `src/routes.ts` and route metadata are intentionally changed.
- Do not call `api/memory.ts` directly from `list.tsx`; use `use-memory.ts` so query keys and enabled gates stay centralized.
- Do not query `/api/memory` before package key and selected private-scope requirements are satisfied.
- Do not treat opaque `memoryId` values as report slugs, download URLs, or routable finance identifiers.
- Do not add namespace wildcard search, vector search, embeddings, chunk tables, or grant-authoring UI to this route.
- Do not duplicate Memory API types in the page. Add wire changes in `src/lib/types/memory.ts` and update hooks/API guides together.

## VALIDATION

```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```

## NOTES

- `list.tsx` keeps access-context and filter form state local to the page.
- Detail, revision, and event reads share the same access request as the list.
- The route is intentionally a scoped inspection surface, not a global memory browser.
