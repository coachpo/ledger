# FRONTEND LIB GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file only covers `src/lib/`.

## OVERVIEW
`src/lib/` owns the frontend API contract, query-key naming, formatting helpers, report grouping helpers, runtime-input row helpers, and shared type definitions for templates, reports, Scheduled Tasks, and the current agent-platform domains.

Extension model: backend extensions are statically installed and expose package-authoring tools through `/api/tools`; frontend routes are static.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## CHILD DOCS
- `api/AGENTS.md` — resource request helpers and upload/download boundaries
- `types/AGENTS.md` — shared TypeScript wire contracts and enum-like unions
- `platform-authoring/AGENTS.md` plus child docs — pure schema/value/ref/package manifest authoring helpers

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| HTTP wrapper / error mapping | `api-client.ts` | `request()`, `requestPlatform()`, `ApiRequestError`, URL helpers |
| API endpoint functions | `api/*.ts` | domain-specific modules for templates, reports, Scheduled Tasks, and agent-platform resources |
| Shared wire types | `types/*.ts` | domain-specific type definitions for preserved product, Scheduled Tasks, and platform routes |
| Query key factory | `query-keys.ts` | hierarchical keys, param normalization, and preserved-product plus platform cache namespaces |
| Display formatting | `format.ts` | currency, decimal, percent, date/datetime, compact numbers |
| Runtime input helpers | `runtime-inputs.ts` | row ids, row-to-map conversion, shared editor/report-generation helpers |
| Workflow option helpers | `workflow-options.ts` | visible fallback option when a saved selection is missing from package workflows |
| Platform authoring helpers | `platform-authoring/AGENTS.md` | schema/value/ref/package manifest IR, codecs, factories, validation |
| Report grouping | `report-grouping.ts` | report list filtering, grouping, and sort helpers |
| Unit coverage | `api.test.ts`, `api/schedules.test.ts`, `query-keys.test.ts`, `format.test.ts` | contract and helper regressions |

## CONVENTIONS
- `api-client.ts` is the only place that should know the base URL, query-string encoding, and error-envelope parsing.
- `api-client.ts` falls back to `http://127.0.0.1:8000/api/v1` only when `VITE_API_BASE_URL` is absent; `start.sh` and Playwright override that value for real runs.
- Domain-specific API functions live in `api/*.ts` modules, organized by resource type.
- Wire decimals remain strings until shared format helpers convert them for display math.
- `query-keys.ts` normalizes ids as strings, symbol lists as trimmed/deduplicated/sorted arrays where relevant, and history params so cache keys stay stable across callers.
- Reports and platform resources use dedicated query-key namespaces.
- Report flows use `queryKeys.reports.*`; `downloadReportUrl()` stays in the API layer because it builds the absolute file URL from the configured API base.
- `runtime-inputs.ts` is the shared translator between editable key/value rows and trimmed `TemplateRuntimeInputs` maps for preview and report generation.
- `workflow-options.ts` keeps package launch schedule/editor selectors stable when a previously selected workflow is absent from the latest package draft.
- `report-grouping.ts` is frontend-only derived-view logic; backend report endpoints stay flat while grouping/search/sort are composed locally.
- Platform flows use `requestPlatform()`-backed helpers and `queryKeys.platform.*`; keep route-specific polling, Scheduled Task invalidation, and mutation policy in hooks rather than embedding it in pages.
- Report detail queries are slug-scoped, not numeric-id scoped, even though some shared helper signatures still use generic `IdParam` naming.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not hard-code endpoint paths or duplicate `request()` / `requestPlatform()` behavior in hooks/components.
- Do not bypass `api-client.ts` and call `fetch` directly.
- Do not create API functions outside the `api/*.ts` domain modules.
- Do not invent new query-key shapes outside `query-keys.ts`.
- Do not duplicate backend contract types when `types/*.ts` already exposes them.
- Do not change template, error-envelope, report, Scheduled Task, or platform contract shapes here without updating the backend contract and the calling hooks/pages.
- Do not change `api/` helpers or `types/` contracts in isolation; keep request helpers and wire shapes in sync.
- Do not mix presentation-only formatting into API wrapper code.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- Route code should import direct modules from `api/*` and `types/*` instead of relying on barrel re-exports.
- `runtime-inputs.ts` is shared by `TemplateEditorPage` and `GenerateReportDialog`; keep those flows aligned when changing row semantics.
- Current unit tests in this folder are helper/API focused; routed and feature-heavy behavior is covered primarily by Playwright and targeted page tests.
