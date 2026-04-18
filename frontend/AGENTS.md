# FRONTEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local frontend docs live throughout `src/**/AGENTS.md`.

## OVERVIEW
React 19 + Vite frontend with a flat route shell, TanStack Query for server state, routed workspace areas for portfolios, templates, reports, and orchestration, plus shared forms and UI that keep route logic thin.

## CHILD DOCS
- `src/lib/AGENTS.md` — API client, query keys, analytics, formatting, runtime-input helpers, shared types
- `src/lib/api/AGENTS.md` — resource API modules for uploads, downloads, and route helpers
- `src/lib/types/AGENTS.md` — shared frontend wire contracts mirroring backend schemas
- `src/hooks/AGENTS.md` — TanStack Query wrappers and invalidation patterns
- `src/pages/AGENTS.md` — routed page components and orchestration patterns
- `src/pages/orchestration/AGENTS.md` — orchestration route family for roles and characters
- `src/pages/simulations/AGENTS.md` — simulation list/config/detail orchestration and polling behavior
- `src/pages/portfolios/AGENTS.md` — portfolio list/detail route orchestration
- `src/pages/templates/AGENTS.md` — template list/editor orchestration and preview rules
- `src/pages/reports/AGENTS.md` — report list/detail flows, markdown edit/download behavior
- `src/components/AGENTS.md` — layout shell, theme system, shared components, forms, feature UI, primitives
- `src/components/forms/AGENTS.md` — shared dialog forms for portfolios and report generation
- `src/components/templates/AGENTS.md` — placeholder browser and runtime-input support components
- `src/components/simulations/AGENTS.md` — simulation charts, metrics, status badges, and trade-log UI
- `src/components/ui/AGENTS.md` — shadcn/ui wrappers, sidebar primitives, and shared variant tokens
- `src/components/shared/AGENTS.md` — reusable tables, metrics, error boundaries, and field schemas
- `src/components/portfolios/AGENTS.md` — portfolio feature sections, dialogs, tables, and trading forms

## STRUCTURE
```text
frontend/
├── src/lib/            # API contract, query keys, formatting, analytics, grouping, types
├── src/hooks/          # TanStack Query hooks wrapping lib/api modules
├── src/pages/          # dashboard, portfolio, template, report, simulation, orchestration routes
├── src/components/     # layout shell, theme, shared UI, forms, templates, portfolio/simulation feature UI, shadcn primitives
├── src/styles/         # fonts, theme tokens, global styles
├── src/test/           # Vitest jsdom setup
├── e2e/                # Playwright smoke, functional, reports, simulations, orchestration specs
└── scripts/            # Playwright backend/frontend startup helpers
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App bootstrap | `src/App.tsx`, `src/routes.ts`, `src/components/layout.tsx` | query client, router provider, layout shell, theme toggle, sidebar navigation |
| Shared API/state logic | `src/lib/AGENTS.md`, `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, `src/hooks/AGENTS.md` | typed fetch, query keys, wire contracts, and TanStack Query wrappers |
| Portfolio routes | `src/pages/portfolios/*.tsx`, `src/components/portfolios/AGENTS.md` | list/detail workspace, balances, positions, trades |
| Template routes | `src/pages/templates/*.tsx`, `src/components/templates/AGENTS.md`, `src/hooks/use-templates.ts`, `src/lib/api/templates.ts` | CRUD, runtime inputs, placeholder tree, inline preview compile |
| Report routes | `src/pages/reports/AGENTS.md`, `src/hooks/use-reports.ts`, `src/lib/api/reports.ts`, `src/lib/report-grouping.ts` | generate from template, upload markdown, group/search, edit/download/delete |
| Simulation routes | `src/pages/simulations/AGENTS.md`, `src/hooks/use-simulations.ts`, `src/lib/api/simulations.ts` | launch simulations, switch launch modes, poll active callback states, charts, result navigation |
| Orchestration routes | `src/pages/orchestration/AGENTS.md`, `src/hooks/use-orchestration.ts`, `src/lib/api/orchestration.ts`, `src/lib/types/orchestration.ts` | roles, characters, mention catalog, route forms |
| Shared components | `src/components/AGENTS.md`, `src/components/forms/AGENTS.md` | layout shell, theme, shared UI, dialog forms, portfolio feature folders |
| UI primitives | `src/components/ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |
| Unit test setup | `vite.config.ts`, `src/test/setup.ts` | jsdom config + browser API mocks |
| E2E flow setup | `playwright.config.ts`, `scripts/start-playwright-*.mjs` | backend `8001`, frontend `4173` |

## CONVENTIONS
- Routing stays flat under `Layout`; feature depth lives inside components and hooks, not in nested route trees.
- `src/routes.ts` is the route source of truth, and `src/components/layout.tsx` owns the shell nav plus breadcrumb labels.
- Server data flows through `src/lib/api*.ts` and `src/hooks/*`; routed screens should not call `fetch` directly.
- Use the `@` alias for `src/` imports instead of long relative paths.
- Mutation-heavy screens use Sonner toasts for success/error feedback and shadcn/ui primitives for dialogs/forms.
- The template editor route is still inside the main shell, but `Layout` gives it a full-height content region instead of the usual scroll container.
- Template preview and report generation both support runtime-input maps built from shared row helpers in `src/lib/runtime-inputs.ts`.
- Report flows are slug-addressed, use `use-reports.ts` for server state, and rely on `downloadReportUrl()` for native markdown downloads.
- Report inventory grouping/search/sort logic lives in `src/lib/report-grouping.ts`; the route composes that derived view state instead of re-implementing grouping inline.
- `GenerateReportDialog` is the shared surface for parameterized report creation from both the template editor and the report list.
- Report content edits intentionally invalidate both report list and slug-scoped detail queries so the detail route stays fresh without a forced navigation round trip.
- Simulation detail uses numeric ids, not slugs, and `useSimulation()` polls every 5 seconds while status is `PENDING`, `RUNNING`, `AWAITING_CALLBACK`, or `PROCESSING_CALLBACK`.
- Simulation creation can either use an existing portfolio/template or create a new portfolio plus initial cash balance before launching the run. The form still exposes legacy `webhookUrl`/`webhookTimeout`, but those fields are only required for `launchMode === "legacy_callback"`; internal execution is the default path.
- Orchestration pages use shared form schemas from `src/components/shared/form-schemas.ts` for role and character CRUD, and `use-orchestration.ts` keeps the query/mutation wiring in one place.
- Theme state lives in `src/components/theme-provider.tsx`; components should consume the existing context instead of inventing new color-mode state.
- Query keys normalize ids as strings, symbol lists as trimmed/deduplicated/sorted arrays where relevant, and orchestration caches under `queryKeys.orchestration.*`.

## ANTI-PATTERNS
- Do not hard-code API URLs or call `fetch` directly from routed screens.
- Do not invent ad-hoc query keys or parse decimal strings in pages when shared helpers already exist.
- Do not put feature-heavy routed screens in `src/components/ui/`.
- Do not change API modules or shared wire types in isolation; update `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, and the calling hooks together.
- Do not change template route, placeholder, or query-key shapes without updating hooks, types, and tests together.
- Do not change runtime-input row behavior, `inputs.*` expectations, or generation-dialog wiring without updating the editor, shared dialog, hooks, and backend compile contract together.
- Do not change report route, slug, upload/download, or query-key shapes without updating hooks, types, and tests together.
- Do not bypass `use-simulations.ts` and hand-roll polling, cancel, or delete state in pages or result widgets.
- Do not move simulation charts or status badges into `src/components/ui/`; they are domain widgets tied to the simulation wire contract.
- Do not add dead routes or unused API modules without wiring them into the actual router and tests.
- Do not hide orchestration route ownership inside generic UI folders or stale docs.

## COMMANDS
```bash
pnpm install
pnpm dev
pnpm preview
```

## VALIDATION
```bash
pnpm lint
pnpm typecheck
pnpm build
pnpm test:run
pnpm test:e2e
```

## NOTES
- `vite.config.ts` sets up the `@` alias, Vitest jsdom mode, and manual chunking for framework/data/ui/forms/date/vendor bundles.
- Playwright only runs Chromium here and starts both backend/frontend web servers automatically via `scripts/start-playwright-*.mjs`, with backend `8001` and frontend `4173`.
- Current Vitest coverage is still selective, but it now spans `src/lib/` helpers plus targeted simulation and orchestration hooks/pages.
- The live router exposes dashboard, portfolio list/detail, template list/editor, report list/detail, simulation list/config/detail, and orchestration index/role/character routes.
