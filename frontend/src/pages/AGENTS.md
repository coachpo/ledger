# FRONTEND PAGES GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers routed page components in `src/pages/`.

## CHILD DOCS
- `agents/AGENTS.md` — agents list and editor route family
- `skills/AGENTS.md` — skills list and editor route family
- `mcp-servers/AGENTS.md` — MCP servers list and editor route family
- `output-schemas/AGENTS.md` — output schemas list and editor route family
- `workflows/AGENTS.md` — workflows list, editor, and run-launch route family
- `runs/AGENTS.md` — runs list and detail route family
- `portfolios/AGENTS.md` — portfolio list/detail workspace routes
- `templates/AGENTS.md` — template list/editor routes and preview rules
- `reports/AGENTS.md` — report list/detail routes and markdown workflows

## OVERVIEW
`src/pages/` contains the routed screen components that map directly to `src/routes.ts`. The shipped route families are the dashboard, preserved portfolio/template/report pages, and the current agent-platform pages for agents, skills, MCP servers, output schemas, workflows, and runs.

## STRUCTURE
```text
src/pages/
├── dashboard.tsx                # home route summary
├── agents/                      # agent list and editor routes
├── skills/                      # skill list and editor routes
├── mcp-servers/                 # MCP server list and editor routes
├── output-schemas/              # output schema list and editor routes
├── workflows/                   # workflow list and editor routes
├── runs/                        # run list and detail routes
├── portfolios/                  # portfolio workspace routes
├── templates/                   # stored-template list/editor routes
├── reports/                     # report inventory and detail routes
└── platform-resource-shared.tsx # shared route helper utilities for platform pages
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Dashboard landing | `dashboard.tsx` | home route summary and retry state |
| Agent-platform pages | `agents/AGENTS.md`, `skills/AGENTS.md`, `mcp-servers/AGENTS.md`, `output-schemas/AGENTS.md`, `workflows/AGENTS.md`, `runs/AGENTS.md` | routed CRUD, workflow authoring, and run inspection |
| Portfolio workspace | `portfolios/AGENTS.md` | portfolio list and detail workspace |
| Template list/editor | `templates/AGENTS.md` | stored-template CRUD, inline compile preview, placeholder browser |
| Report routes | `reports/AGENTS.md` | list/detail, upload/generate, markdown view/edit/download |
| Shared platform page helpers | `platform-resource-shared.tsx` | common badges, JSON helpers, and small route-level utilities |

## CONVENTIONS
- Each page component maps to exactly one route in `src/routes.ts`.
- `src/routes.ts` owns the route table, while `src/components/layout.tsx` owns the shell, breadcrumbs, and sidebar labels.
- Pages compose hooks from `src/hooks/`, shared components from `src/components/shared/`, and route-specific helpers from nearby files.
- Pages handle top-level data fetching, mutation feedback, and route-level error states, but business rules stay in hooks or shared helpers.
- The template editor page uses `useDebounce()`, `useCompileInline()`, and `usePlaceholders()` to keep preview and placeholder browsing responsive without moving that logic into the component library.
- Portfolio detail pages compose portfolio, balance, position, trade, and market-data hooks together; quote enrichment and allocation math stay in shared analytics helpers instead of the page body.
- Agent-platform pages keep CRUD, authoring, and run inspection in the routed page layer while shared widgets stay reusable and presentational.

## ANTI-PATTERNS
- Do not put business rules or complex state management directly in page components.
- Do not duplicate feature-specific logic here when a feature folder or hook already owns it.
- Do not call `fetch` directly; use hooks from `src/hooks/` instead.
- Do not create ad-hoc query keys in pages; use canonical keys from `src/lib/query-keys.ts`.
- Do not bypass the layout shell, error boundary, or template-editor full-height layout rules when adding a new page.
- Do not duplicate report request logic in page components when `use-reports.ts` and the template editor already own the server-side workflow.
- Do not add dead routes or stale route docs that are not wired into `src/routes.ts`.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm test:e2e
```

## NOTES
- Pages are thin route-layer components; the real complexity lives in hooks, shared components, and nearby page helpers.
- Portfolio detail pages are routable but not exposed separately in the sidebar.
- The live router exposes dashboard, portfolio list/detail, template list/editor, report list/detail, and the current agent-platform routes.
