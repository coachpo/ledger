# FRONTEND EXTENSIONS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/extensions/` is a stale `/extensions` route family scheduled for Task 5.3 deletion. The backend extension state API has been removed; do not add new UI, toggles, tests, or callers here.

Extension model: backend extensions are statically installed through `INSTALLED_EXTENSIONS`; there is no frontend extension state contract to maintain.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task              | Location                                                                                            | Notes                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Extensions route  | `list.tsx`                                                                                          | stale route pending deletion |
| State hooks       | `../../hooks/use-extensions.ts`                                                                     | stale hook pending deletion |
| Runtime ownership | `../../extensions/AGENTS.md`, `../../extensions/runtime.tsx`, `../../extensions/runtime-helpers.ts` | stale host pending deletion |
| Route coverage    | `list.test.tsx`                                                                                     | stale coverage pending deletion |

## CONVENTIONS

- `frontend/DESIGN.md` is the source of truth for this route's page layout, shared shells, tokens, and management UI patterns.
- Do not add backend-contract rendering, sorting, toast feedback, invalidation, or route-level states here; this route is no longer backed by a live API.
- `/extensions` is deletion scope, not `inventory` or `systemState`; do not add search, selection, bulk actions, or filter bars.
- Use shared state/list primitives allowed by `DESIGN.md` so this page stays visually aligned with other platform/system routes.
- Treat this page as removal-only scope. Route/nav/tool visibility should be static after Task 5.3.
- Remove `/extensions` route metadata and regression coverage in Task 5.3.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add marketplace, install, remove, contribution-browser, enable, or disable behavior here.
- Do not mirror private registry or scaffold metadata in the UI.
- Do not use `useToggleExtension()` or duplicate finance visibility rules in the page layer.
- Do not turn this route into a generic settings dump.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/extensions/list.test.tsx
```

## NOTES

- This folder remains only until Task 5.3 removes the frontend plugin host.
- Changes here should be deletion-only unless Task 5.3 is actively in progress.
