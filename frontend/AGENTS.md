# FRONTEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local frontend docs live in `e2e/` and throughout the high-signal `src/**/AGENTS.md` boundaries.

## OVERVIEW
React 19 + Vite frontend with a flat route shell, TanStack Query for server state, extension-assembled Finance Workspace routes, routed workspace areas for Extensions, Workflow Packages, Model Connections, and Runs, plus shared UI that keeps route logic thin. Workflow Packages are the only live executable agent workflow authoring and launch surface.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

Future frontend upgrade work must keep platform-core route, query, and authoring behavior separate from extension-owned route/nav/tool contributions. Do not let Finance Workspace assumptions leak into generic frontend contracts without an explicit shared-contract change.

## CHILD DOCS
- `e2e/AGENTS.md` — Playwright fixed-port startup, route-family specs, and E2E conventions
- `src/extensions/AGENTS.md` — frontend extension registry, route/nav/tool filtering, and Finance Workspace scaffold
- `src/lib/AGENTS.md` — API client, query keys, formatting, runtime-input helpers, platform-authoring helpers, and shared types
- `src/lib/api/AGENTS.md` — resource API modules for uploads, downloads, and route helpers
- `src/lib/types/AGENTS.md` — shared frontend wire contracts mirroring backend schemas
- `src/lib/platform-authoring/AGENTS.md` — pure schema/value/ref/manifest authoring helpers
- `src/hooks/AGENTS.md` — TanStack Query wrappers and invalidation patterns
- `src/pages/AGENTS.md` — routed page components and route-family orchestration patterns
- `src/pages/workflow-packages/AGENTS.md` — package list, editor, validation, preflight, launch, import, and export flows
- `src/pages/runs/AGENTS.md` — runs list, detail, rerun/step-replay, package provenance, polling monitor, and trace-link views
- `src/components/AGENTS.md` — layout shell, theme system, shared components, platform-authoring widgets, feature UI, and primitives
- `src/components/platform-authoring/AGENTS.md` — schema composer, generated form, refs, inspectors, and workflow-builder widgets
- `src/components/templates/AGENTS.md` — placeholder browser and runtime-input support components
- `src/components/ui/AGENTS.md` — shadcn/ui wrappers, sidebar primitives, and shared variant tokens
- `src/components/shared/AGENTS.md` — reusable tables, ResourceRowCard, metrics, error boundaries, and field schemas
- `src/components/portfolios/AGENTS.md` — portfolio feature sections, dialogs, tables, and trading forms
- `retired/global-authoring/src/pages/AGENTS.md` — archive-only global-authoring guide tree; do not treat as live route ownership

## STRUCTURE
```text
frontend/
├── src/extensions/     # frontend extension registry, route/nav assembly, and tool filtering
├── src/lib/            # API contract, query keys, formatting, analytics, grouping, types, platform-authoring helpers
├── src/hooks/          # TanStack Query hooks wrapping lib/api modules
├── src/pages/          # dashboard, extensions, finance workspace, and agent-platform routes
├── src/components/     # layout shell, theme, shared UI, cross-route dialogs, platform-authoring widgets, templates, portfolio UI, shadcn primitives
├── src/styles/         # fonts, theme tokens, and global CSS entrypoints; covered here
├── src/test/           # Vitest jsdom setup; covered here
├── e2e/                # Playwright smoke and functional coverage
└── scripts/            # Playwright backend/frontend startup helpers; covered here
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App bootstrap | `src/App.tsx`, `src/routes.ts`, `src/extensions/runtime.tsx`, `src/components/layout.tsx` | query client, router provider, extension route assembly, layout shell, theme toggle, sidebar navigation |
| Extension runtime and state | `src/extensions/AGENTS.md`, `src/extensions/runtime.tsx`, `src/hooks/use-extensions.ts`, `src/pages/extensions/list.tsx` | bundled frontend extensions, finance route/nav/tool filtering, `/extensions` state UI |
| Shared API/state logic | `src/lib/AGENTS.md`, `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, `src/lib/platform-authoring/AGENTS.md`, `src/hooks/AGENTS.md` | typed fetch, query keys, wire contracts, platform-authoring helpers, and TanStack Query wrappers |
| Portfolio routes | `src/pages/portfolios/list.tsx`, `src/pages/portfolios/detail.tsx`, `src/components/portfolios/AGENTS.md` | list/detail workspace, balances, positions, trades |
| Template routes | `src/pages/templates/list.tsx`, `src/pages/templates/editor.tsx`, `src/components/templates/AGENTS.md`, `src/hooks/use-templates.ts`, `src/lib/api/templates.ts` | CRUD, runtime inputs, placeholder tree, inline preview compile |
| Report routes | `src/pages/reports/list.tsx`, `src/pages/reports/detail.tsx`, `src/hooks/use-reports.ts`, `src/lib/api/reports.ts`, `src/lib/report-grouping.ts` | generate from template, upload markdown, group/search, edit/download/delete |
| Agent-platform routes | `src/pages/workflow-packages/AGENTS.md`, `src/pages/model-connections/list.tsx`, `src/pages/model-connections/editor.tsx`, `src/pages/runs/AGENTS.md` | Workflow Packages, Model Connections, and Runs |
| Shared components | `src/components/AGENTS.md`, `src/components/platform-authoring/AGENTS.md`, `src/components/forms/*.tsx` | layout shell, theme, shared UI, cross-route dialogs, platform-authoring widgets, portfolio feature folders |
| UI primitives | `src/components/ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |
| Unit test setup | `vite.config.ts`, `src/test/setup.ts` | jsdom config plus browser API mocks |
| E2E flow setup | `playwright.config.ts`, `scripts/start-playwright-*.mjs` | backend `8001`, frontend `4173` |
| Archive-only global authoring context | `retired/global-authoring/src/pages/AGENTS.md` | removed standalone authoring surfaces; cutover context only |

## CONVENTIONS
- Routing stays flat under `Layout`; feature depth lives inside components and hooks, not in nested route trees.
- `src/routes.ts` is the route source of truth, with Finance Workspace route entries assembled from `src/extensions/runtime.tsx`; `src/components/layout.tsx` owns the shell nav plus breadcrumb labels.
- Server data flows through `src/lib/api*.ts` and `src/hooks/*`; routed screens should not call `fetch` directly.
- Keep React render logic pure; use effects only for external synchronization, not derived state or local data transforms.
- Browser-exposed env access goes through `import.meta.env`, and only `VITE_`-prefixed variables may reach frontend code.
- Use the `@` alias for `src/` imports instead of long relative paths.
- Mutation-heavy screens use Sonner toasts for success/error feedback and shadcn/ui primitives for dialogs/forms.
- Template and workflow package editor routes stay inside the main shell, but `Layout` gives them full-height content regions instead of the usual scroll container.
- Template preview and report generation both support runtime-input maps built from shared row helpers in `src/lib/runtime-inputs.ts`.
- Report flows are slug-addressed, use `use-reports.ts` for server state, and rely on `downloadReportUrl()` for native markdown downloads.
- Report inventory grouping/search/sort logic lives in `src/lib/report-grouping.ts`; the route composes that derived view state instead of re-implementing grouping inline.
- `GenerateReportDialog` is the shared surface for parameterized report creation from both the template editor and the report list.
- Workflow package editors are YAML-manifest editors with local package-resource editing, backend validation, preflight, launch, import, export, and schema-driven run-input forms.
- Agent-platform pages use dedicated hooks and route params to keep package CRUD, extension-filtered global Tools reads, global Model Connections, and Run inspection inside the routed page layer.
- `useExtensions()` drives Finance Workspace route/nav visibility, `/extensions` state UI, and tool filtering for package capability profiles.
- The `/extensions` page is a system state surface only; render only the backend contract (`key`, `label`, `enabled`) and keep marketplace/install/remove behavior out of phase 1.
- Model connection editors keep credentials write-only in the UI: blank edit submissions preserve the stored key, and inline connection tests run against the persisted backend connection only after save.
- This parent guide owns `src/styles/`, `src/test/`, and `scripts/` because those folders are still small. Split them back out only if they gain independent ownership or materially different rules.
- `src/styles/` owns global Tailwind/theme entrypoints only; keep one-off layout and feature styling in components instead of growing the global layer.
- `src/test/setup.ts` owns global jsdom/browser shims only; route-specific mocks, network mocks, and feature data factories stay with the owning tests.
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
- Do not hard-code Finance Workspace visibility outside `src/extensions/runtime.tsx` and `use-extensions.ts`.
- Do not treat `retired/**` files as live route ownership or as a shortcut for new package-first UI.
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
- The live router exposes dashboard, extension-gated portfolio/template/report routes, `/extensions`, Workflow Packages, Model Connections, and Runs; retired route families are guarded in `src/routes.test.tsx`.
