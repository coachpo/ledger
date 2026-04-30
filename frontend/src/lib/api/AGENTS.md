# FRONTEND API MODULES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/lib/AGENTS.md`.

## OVERVIEW
`src/lib/api/` contains resource-specific request helpers layered on top of `api-client.ts`. These modules are the only frontend code that should know endpoint paths, the preserved `/api/v1` versus current `/api/*` split, multipart upload details, and download URL construction.

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
├── agents.ts              # agent-platform agent CRUD and run helpers
├── capabilities.ts        # capability CRUD and activation
├── mcp-servers.ts         # MCP server CRUD and connection testing
├── output-schemas.ts      # output schema CRUD and version reads
├── workflows.ts           # workflow CRUD and run launch
└── runs.ts                # run list/detail reads
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared fetch/error behavior | `../api-client.ts` | base URL, error envelope parsing, query encoding, v1 and platform helpers |
| Preserved product contracts | `portfolios.ts`, `balances.ts`, `positions.ts`, `trading-operations.ts`, `market-data.ts`, `templates.ts`, `reports.ts` | browser-facing `/api/v1` helpers |
| Agent-platform contracts | `agents.ts`, `capabilities.ts`, `mcp-servers.ts`, `model-connections.ts`, `output-schemas.ts`, `workflows.ts`, `runs.ts` | browser-facing `/api/*` helpers |
| CSV import endpoints | `positions.ts` | preview/commit upload helpers |
| Report download helper | `reports.ts` | builds the absolute markdown download URL |

## CONVENTIONS
- One module per backend resource family; keep path helpers and request bodies close to that resource.
- Route network calls through `request()` or `requestPlatform()` from `api-client.ts`.
- Keep upload/download specifics here: multipart report upload, CSV preview/commit, and markdown download URLs should not leak into hooks or pages.
- Keep preserved `/api/v1` resource paths and current unversioned platform `/api/*` paths separate in the module layer.
- Match backend casing exactly; request/response types come from `../types/*` rather than inline object literals.

## ANTI-PATTERNS
- Do not call `fetch` directly from hooks or pages when a helper belongs here.
- Do not mix multiple resource domains into one helper file just because one screen uses them together.
- Do not put toasts, navigation, or React state in this directory.
- Do not hand-build download paths outside `reports.ts`; keep absolute URL generation centralized.
- Do not bypass `request()` or `requestPlatform()` for shipped routes.

## NOTES
- The frontend no longer ships legacy v2, Studio, Tryout, or orchestration API helpers in this folder.
- Platform resources use the unversioned `/api/*` helpers, while portfolios, templates, and reports stay on `/api/v1`.
- Keep this file aligned with `src/hooks/AGENTS.md`, `src/lib/types/AGENTS.md`, and the live files under `src/lib/api/`.
