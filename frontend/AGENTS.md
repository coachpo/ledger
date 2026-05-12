# FRONTEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local frontend docs live in `e2e/`, `scripts/`, and throughout `src/**/AGENTS.md`.

## OVERVIEW
React 19 + Vite frontend with a flat route shell, TanStack Query for server state, routed workspace areas for portfolios, templates, reports, Workflow Packages, Model Connections, and Runs, plus shared forms and UI that keep route logic thin.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## CHILD DOCS
- `e2e/AGENTS.md` — Playwright fixed-port startup, route-family specs, and E2E conventions
- `scripts/AGENTS.md` — Playwright backend/frontend startup helpers
- `src/styles/AGENTS.md` — Tailwind v4 imports, theme tokens, dark variant, and empty font stub
- `src/test/AGENTS.md` — Vitest jsdom setup and browser API mocks
- `src/lib/AGENTS.md` — API client, query keys, formatting, runtime-input helpers, platform-authoring helpers, shared types
- `src/lib/api/AGENTS.md` — resource API modules for uploads, downloads, and route helpers
- `src/lib/types/AGENTS.md` — shared frontend wire contracts mirroring backend schemas
- `src/lib/platform-authoring/AGENTS.md` — pure schema/value/ref/manifest authoring helpers
- `src/hooks/AGENTS.md` — TanStack Query wrappers and invalidation patterns
- `src/pages/AGENTS.md` — routed page components and route-family orchestration patterns
- `src/pages/workflow-packages/AGENTS.md` — package list, editor, validation, preflight, launch, import, and export flows
- `src/pages/model-connections/AGENTS.md` — saved model connection list, editor, secret preservation, delete flow, and connection-test flows
- `src/pages/runs/AGENTS.md` — runs list, detail, rerun/step-replay, package provenance, polling monitor, and trace-link views
- `src/pages/portfolios/AGENTS.md` — portfolio list/detail route orchestration
- `src/pages/templates/AGENTS.md` — template list/editor orchestration and preview rules
- `src/pages/reports/AGENTS.md` — report list/detail flows, markdown edit/download behavior
- `src/components/AGENTS.md` — layout shell, theme system, shared components, forms, platform-authoring widgets, feature UI, primitives
- `src/components/platform-authoring/AGENTS.md` — schema composer, generated form, refs, inspectors, and workflow-builder widgets
- `src/components/forms/AGENTS.md` — shared dialog forms, SecretInput, and report generation
- `src/components/templates/AGENTS.md` — placeholder browser and runtime-input support components
- `src/components/ui/AGENTS.md` — shadcn/ui wrappers, sidebar primitives, and shared variant tokens
- `src/components/shared/AGENTS.md` — reusable tables, ResourceRowCard, metrics, error boundaries, and field schemas
- `src/components/portfolios/AGENTS.md` — portfolio feature sections, dialogs, tables, and trading forms

## STRUCTURE
```text
frontend/
├── src/lib/            # API contract, query keys, formatting, analytics, grouping, types, platform-authoring helpers
├── src/hooks/          # TanStack Query hooks wrapping lib/api modules
├── src/pages/          # dashboard, portfolio, template, report, and agent-platform routes
├── src/components/     # layout shell, theme, shared UI, forms, platform-authoring widgets, templates, portfolio UI, shadcn primitives
├── src/styles/         # fonts, theme tokens, global styles
├── src/test/           # Vitest jsdom setup
├── e2e/                # Playwright smoke and functional coverage
└── scripts/            # Playwright backend/frontend startup helpers
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App bootstrap | `src/App.tsx`, `src/routes.ts`, `src/components/layout.tsx` | query client, router provider, layout shell, theme toggle, sidebar navigation |
| Shared API/state logic | `src/lib/AGENTS.md`, `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, `src/lib/platform-authoring/AGENTS.md`, `src/hooks/AGENTS.md` | typed fetch, query keys, wire contracts, platform-authoring helpers, and TanStack Query wrappers |
| Portfolio routes | `src/pages/portfolios/*.tsx`, `src/components/portfolios/AGENTS.md` | list/detail workspace, balances, positions, trades |
| Template routes | `src/pages/templates/*.tsx`, `src/components/templates/AGENTS.md`, `src/hooks/use-templates.ts`, `src/lib/api/templates.ts` | CRUD, runtime inputs, placeholder tree, inline preview compile |
| Report routes | `src/pages/reports/AGENTS.md`, `src/hooks/use-reports.ts`, `src/lib/api/reports.ts`, `src/lib/report-grouping.ts` | generate from template, upload markdown, group/search, edit/download/delete |
| Agent-platform routes | `src/pages/workflow-packages/AGENTS.md`, `src/pages/model-connections/AGENTS.md`, `src/pages/runs/AGENTS.md` | Workflow Packages, Model Connections, Runs |
| Preserved product routes | `src/pages/portfolios/AGENTS.md`, `src/pages/templates/AGENTS.md`, `src/pages/reports/AGENTS.md` | portfolio, template, and report routes |
| Shared components | `src/components/AGENTS.md`, `src/components/platform-authoring/AGENTS.md`, `src/components/forms/AGENTS.md` | layout shell, theme, shared UI, platform-authoring widgets, dialog forms, portfolio feature folders |
| UI primitives | `src/components/ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |
| Unit test setup | `vite.config.ts`, `src/test/setup.ts` | jsdom config plus browser API mocks |
| E2E flow setup | `playwright.config.ts`, `scripts/start-playwright-*.mjs` | backend `8001`, frontend `4173` |

## CONVENTIONS
- Routing stays flat under `Layout`; feature depth lives inside components and hooks, not in nested route trees.
- `src/routes.ts` is the route source of truth, and `src/components/layout.tsx` owns the shell nav plus breadcrumb labels.
- Server data flows through `src/lib/api*.ts` and `src/hooks/*`; routed screens should not call `fetch` directly.
- Use the `@` alias for `src/` imports instead of long relative paths.
- Mutation-heavy screens use Sonner toasts for success/error feedback and shadcn/ui primitives for dialogs/forms.
- Template and workflow package editor routes stay inside the main shell, but `Layout` gives them full-height content regions instead of the usual scroll container.
- Template preview and report generation both support runtime-input maps built from shared row helpers in `src/lib/runtime-inputs.ts`.
- Report flows are slug-addressed, use `use-reports.ts` for server state, and rely on `downloadReportUrl()` for native markdown downloads.
- Report inventory grouping/search/sort logic lives in `src/lib/report-grouping.ts`; the route composes that derived view state instead of re-implementing grouping inline.
- `GenerateReportDialog` is the shared surface for parameterized report creation from both the template editor and the report list.
- Workflow package editors are YAML-manifest editors with local package-resource editing, backend validation, preflight, launch, import, export, and schema-driven run-input forms.
- Agent-platform pages use dedicated hooks and route params to keep package CRUD, global Model Connections, global Tools reads, and Run inspection inside the routed page layer.
- Theme state lives in `src/components/theme-provider.tsx`; components should consume the existing context instead of inventing new color-mode state.
- Query keys normalize ids as strings, symbol lists as trimmed/deduplicated/sorted arrays where relevant, and portfolio, template, report, and agent-platform caches under dedicated namespaces.

## ANTI-PATTERNS
- Do not hard-code API URLs or call `fetch` directly from routed screens.
- Do not invent ad-hoc query keys or parse decimal strings in pages when shared helpers already exist.
- Do not put feature-heavy routed screens in `src/components/ui/`.
- Do not change API modules or shared wire types in isolation; update `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, and the calling hooks together.
- Do not change template route, placeholder, or query-key shapes without updating hooks, types, and tests together.
- Do not change runtime-input row behavior, `inputs.*` expectations, or generation-dialog wiring without updating the editor, shared dialog, hooks, and backend compile contract together.
- Do not change report route, slug, upload/download, or query-key shapes without updating hooks, types, and tests together.
- Do not add dead routes or unused API modules without wiring them into the actual router and tests.
- Do not document retired `/skills`, `/studio`, `/tryout`, `/orchestration`, `/backtests`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` routes as live surfaces.
- Do not hide package-first route ownership inside generic UI folders or stale docs.

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
- Current Vitest coverage spans `src/lib/` helpers plus targeted agent-platform, template-editor, and layout pages.
- `src/styles/fonts.css` is empty/unreferenced; theme tokens live in `src/styles/theme.css` and Tailwind import/source control lives in `src/styles/tailwind.css`.
- The live router exposes dashboard, portfolio list/detail, template list/editor, report list/detail, and the current agent-platform routes; retired route families are guarded in `src/routes.test.tsx`.
