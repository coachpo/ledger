# FRONTEND SCHEDULED TASKS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/scheduled-tasks/` owns the package-first automation route family for recurring Workflow Package runs. The list route monitors saved schedules, the create route authors one package/workflow schedule, and the detail route is the console for recurrence, scheduled input previews, run-now, delete, fire history, and linked run evidence.

Scheduled Tasks are platform-owned. They are not a Finance Workspace extension route and they are not raw cron authoring.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## STRUCTURE
```text
scheduled-tasks/
|-- list.tsx         # inventory, package/workflow filters, status actions, run-now entry
|-- editor.tsx       # create flow, package/workflow target, preview, save
|-- detail.tsx       # full-height console for edit, preview, fire history, delete
|-- list.test.tsx    # inventory states, package/workflow filters, links, actions
`-- detail.test.tsx  # detail tabs, preview, run-now, delete, redirect states
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Schedule inventory | `list.tsx` | package/workflow filters, sortable table, selection, explicit open/delete/run-now/pause-resume actions |
| Schedule creation | `editor.tsx` | creates one schedule for a saved package id and workflow key, with preview before save |
| Schedule console | `detail.tsx` | recurrence editor, JSON template/vars editor, preview, run-now, delete, fire history, latest run links |
| Schedule hooks | `../../hooks/use-scheduled-tasks.ts` | list/detail/fire queries, create/update/delete/preview/run-now mutations, linked run invalidation |
| Wire/API contracts | `../../lib/api/schedules.ts`, `../../lib/types/schedule.ts` | `/api/schedules` helpers plus recurrence, fire, preview, run-now, and 204 delete payloads |
| Runtime input helpers | `../../hooks/use-workflow-packages.ts`, `../../lib/runtime-inputs.ts` | saved personal runtime inputs and trimmed row-to-map conversion |
| Route metadata | `../../routes.metadata.ts` | list is inventory/scroll/wide, new is editor/fullHeight/full, detail is console/fullHeight/full |
| Coverage | `list.test.tsx`, `detail.test.tsx`, `../../hooks/use-scheduled-tasks.test.ts`, `../../lib/api/schedules.test.ts` | route behavior, hook invalidation, and API endpoint contracts |

## CONVENTIONS
- Structured recurrence only: interval, daily, weekly, or monthly. Do not introduce raw cron strings in this route family.
- IANA timezone and backend occurrence calculation are authoritative; UI helpers may format local hints but must not fork DST or monthly-date semantics.
- Scheduled input templates and template vars are JSON objects. Allow placeholders only from `schedule.*`, `fire.*`, `window.*`, `lastRun.*`, and `vars.<key>`.
- Treat preview responses as the source of truth for rendered parameters and validation errors. Local placeholder checks are assistance only.
- `run-now` requires `idempotencyKey` and `scheduledFor`, creates a manual fire, then links operators to the returned run detail for queue/execution evidence.
- Delete uses the schedule delete mutation, confirms destructive intent, and redirects detail users back to `/scheduled-tasks` after success. The page should not preserve a deleted-schedule state.
- List rows/cards use explicit links and buttons. Do not make entire cards or rows pointer-only open targets.
- Fire history stays schedule-owned; run detail owns execution evidence after a fire has queued a run.
- Keep wide JSON templates, fire metadata, and run links mobile-contained with wrapping or internal scroll.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not fetch schedules directly from pages; use `use-scheduled-tasks.ts`.
- Do not store schedule query keys outside `queryKeys.platform.schedules`.
- Do not treat Scheduled Tasks as extension-gated finance UI.
- Do not reintroduce removed search/status filters, soft-delete mutations, or read-only deleted branches.
- Do not derive run execution state from fire status when the linked run payload is available.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/scheduled-tasks/list.test.tsx src/pages/scheduled-tasks/detail.test.tsx src/hooks/use-scheduled-tasks.test.ts src/lib/api/schedules.test.ts
```
