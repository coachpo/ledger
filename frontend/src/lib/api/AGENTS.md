# FRONTEND API MODULES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/api/` contains resource-specific request helpers layered on top of `api-client.ts`. These modules are the only frontend code that should know endpoint paths, API-version boundaries, multipart upload details, and download URL construction.

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
├── orchestration.ts       # v1 roles, characters, mention catalog
├── runtime.ts             # v2 runtime runs, approvals, trace
├── studio.ts              # v2 Studio reads for runs, artifacts, approvals, trace
├── tryouts.ts             # v2 Tryout execute/read/persist
├── workflow-specs.ts      # v2 workflow catalog and lifecycle actions
├── agent-specs.ts         # v2 agent-spec catalog and lifecycle actions
├── capabilities.ts        # v2 capability catalog and lifecycle actions
└── personas.ts            # v2 persona profile reads and lifecycle actions
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared fetch/error behavior | `../api-client.ts` | base URL, error envelope parsing, query encoding, v1/v2 helpers |
| Template contract | `templates.ts` | stored CRUD, inline compile, placeholder tree |
| Report contract | `reports.ts` | slug-based reads, compile, upload, download helper |
| Orchestration contract | `orchestration.ts` | role/character CRUD plus mention catalog |
| Runtime contract | `runtime.ts` | run list/detail/create/cancel, approvals, trace |
| Studio reads | `studio.ts` | runs, artifacts, approvals, trace-event reads |
| Tryout contract | `tryouts.ts` | execute, read, persist a Tryout-backed run |
| Studio catalog endpoints | `workflow-specs.ts`, `agent-specs.ts`, `capabilities.ts`, `personas.ts` | managed catalog reads and lifecycle actions |
| CSV import endpoints | `positions.ts` | preview/commit upload helpers |
| Market data endpoints | `market-data.ts` | quotes/history query serialization |

## CONVENTIONS
- One module per backend resource family; keep path helpers and request bodies close to that resource.
- Always route network calls through `request()`, `requestV2()`, or `buildUrl()` from `api-client.ts`.
- Keep upload/download specifics here: multipart report upload, CSV preview/commit, and markdown download URLs should not leak into hooks or pages.
- Keep v1 browser resource paths and v2 runtime/catalog paths separate in the module layer.
- `orchestration.ts` mirrors the current backend contract for roles, characters, and mention catalog access; keep hooks/pages thin around it.
- `runtime.ts`, `studio.ts`, and `tryouts.ts` mirror the live v2 contract for runtime runs, approval actions, Studio inspection reads, and Tryout execute/persist flows.
- Match backend casing exactly; request/response types come from `../types/*` rather than inline object literals.

## ANTI-PATTERNS
- Do not call `fetch` directly from hooks or pages when a helper belongs here.
- Do not mix multiple resource domains into one helper file just because the UI screen uses them together.
- Do not put toasts, navigation, or React state in this directory.
- Do not hand-build download paths outside `reports.ts`; keep absolute URL generation centralized.
- Do not bypass `request()` / `requestV2()` for orchestration, runtime, Studio, or Tryout routes.

## NOTES
- The frontend no longer has a live `simulations.ts` browser-facing helper. Document runtime, Studio, and Tryout as the shipped execution surfaces instead.
- `runtime.ts` and `studio.ts` intentionally overlap on run/artifact/trace reads because the product exposes both public runtime views and Studio inspection views.
- `workflow-specs.ts`, `agent-specs.ts`, `capabilities.ts`, and `personas.ts` are Studio-facing catalog modules and should stay aligned with `use-studio.ts`.
