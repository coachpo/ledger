# FRONTEND API MODULES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/api/` contains resource-specific request helpers layered on top of `../api-client.ts`. These modules are the only frontend code that should know endpoint paths, the preserved `/api/v1` versus current `/api/*` split, multipart upload details, and download URL construction.

Extension model: statically resident extension state.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## STRUCTURE
```text
src/lib/api/
├── portfolios.ts          # portfolio CRUD
├── balances.ts            # portfolio-scoped balance CRUD
├── positions.ts           # position CRUD, lookup, CSV preview/commit
├── trading-operations.ts  # BUY/SELL/DIVIDEND/SPLIT requests
├── market-data.ts         # quotes and history requests
├── templates.ts           # template CRUD, compile, placeholder tree
├── reports.ts             # list/detail, compile, upload, download URL
├── extensions.ts          # statically resident extension list/toggle state
├── workflow-packages.ts   # package manifest, version, runtime-input registry, secret bindings, preflight, launch, import, export
├── schedules.ts           # Scheduled Task CRUD, preview, fire history, and run-now requests
├── tools.ts               # read-only server-declared tool catalog
├── model-connections.ts   # saved model endpoint CRUD and connection testing
└── runs.ts                # run list/detail reads with package provenance, progress, queue, and rerun contracts
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared fetch/error behavior | `../api-client.ts` | base URL, error envelope parsing, query encoding, v1 and platform helpers |
| Preserved product contracts | `portfolios.ts`, `balances.ts`, `positions.ts`, `trading-operations.ts`, `market-data.ts`, `templates.ts`, `reports.ts` | browser-facing `/api/v1` helpers |
| Agent-platform contracts | `extensions.ts`, `workflow-packages.ts`, `schedules.ts`, `tools.ts`, `model-connections.ts`, `runs.ts` | package-first `/api/*` helpers for extension state, package authoring, runtime-input registry/history, package secret bindings, Scheduled Tasks, read-only tool metadata, model bindings, and run inspection |
| CSV import endpoints | `positions.ts` | preview/commit upload helpers |
| Report download helper | `reports.ts` | builds the absolute markdown download URL |

## CONVENTIONS
- One module per backend resource family; keep path helpers and request bodies close to that resource.
- Route network calls through `request()` or `requestPlatform()` from `../api-client.ts`.
- Keep upload/download specifics here: multipart report upload, CSV preview/commit, and markdown download URLs should not leak into hooks or pages.
- Keep preserved `/api/v1` resource paths and current unversioned platform `/api/*` paths separate in the module layer.
- `schedules.ts` owns `/api/schedules` path helpers for list/detail/create/update/delete, fire history, unsaved/saved preview, and run-now; do not split run-now into run helpers.
- `workflow-packages.ts` owns package runtime-input registry/history and secret-binding helpers; do not hide those package-scoped APIs inside route components or generic run helpers.
- Match backend casing exactly; request/response types come from `../types/*` rather than inline object literals.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not call `fetch` directly from hooks or pages when a helper belongs here.
- Do not mix multiple resource domains into one helper file just because one screen uses them together.
- Do not put toasts, navigation, or React state in this directory.
- Do not hand-build download paths outside `reports.ts`; keep absolute URL generation centralized.
- Do not bypass `request()` or `requestPlatform()` for shipped routes.

## NOTES
- The frontend does not ship v2, Studio, Tryout, or orchestration API helpers in this folder.
- Platform resources, including extension state, Scheduled Tasks, and global tool discovery for package authoring, use the unversioned `/api/*` helpers, while portfolios, templates, and reports stay on `/api/v1`.
- Keep this file aligned with `src/hooks/AGENTS.md`, `src/lib/types/AGENTS.md`, and the live files under `src/lib/api/`.
