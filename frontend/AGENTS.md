# FRONTEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local frontend docs live in `e2e/` and throughout the high-signal `src/**/AGENTS.md` boundaries.

## OVERVIEW
React 19 + Vite frontend with a flat, metadata-driven route shell, TanStack Query for server state, extension-assembled Finance Workspace routes, routed workspace areas for Extensions, Workflow Packages, Scheduled Tasks, Model Connections, Memory, and Runs, plus shared inventory/workspace UI that keeps route logic thin. Workflow Packages are the only live executable agent workflow authoring and launch surface; Scheduled Tasks are the package-first automation surface for recurring runs.

Extension model: SignalDeck Core ships statically resident extensions in code, while frontend state and gates decide which routes, nav items, and tool pickers are exposed.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

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
- `src/pages/extensions/AGENTS.md` — `/extensions` system state route, slim statically resident extension contract, and toggle behavior
- `src/pages/model-connections/AGENTS.md` — global model endpoint inventory/editor, write-only secrets, and connection-test flows
- `src/pages/memory/AGENTS.md` — `/memory` platform memory inventory, explicit-scope access context, and inline detail/revision/event panes
- `src/pages/portfolios/AGENTS.md` — portfolio list/detail workspace, metrics, balances, positions, and trades
- `src/pages/reports/AGENTS.md` — report inventory/detail, upload, generation, grouping, batch actions, and markdown editing
- `src/pages/templates/AGENTS.md` — stored-template inventory/editor, inline compile preview, runtime inputs, and saved-template report generation
- `src/pages/workflow-packages/AGENTS.md` — package list, authoring-only editor, dedicated `/workflow-packages/:packageId/run` launch page, validation, import, and export flows
- `src/pages/scheduled-tasks/AGENTS.md` — scheduled package-run automation list, create, detail, preview, fire history, and run-now flows
- `src/pages/runs/AGENTS.md` — runs list, detail, root-parameter rerun, invocation-input fork, package provenance, polling monitor, trace-link views, and historical replay lineage reads
- `src/components/AGENTS.md` — layout shell, theme system, shared components, platform-authoring widgets, feature UI, and primitives
- `src/components/platform-authoring/AGENTS.md` — schema composer, generated form, refs, inspectors, and workflow-builder widgets
- `src/components/templates/AGENTS.md` — placeholder browser and runtime-input support components
- `src/components/ui/AGENTS.md` — shadcn/ui wrappers, sidebar primitives, and shared variant tokens
- `src/components/shared/AGENTS.md` — reusable inventory/workspace shells, resource chrome, evidence helpers, tables, and field schemas
- `src/components/portfolios/AGENTS.md` — portfolio feature sections, dialogs, tables, and trading forms

## STRUCTURE
```text
frontend/
├── src/extensions/     # frontend extension registry, route/nav assembly, and tool filtering
├── src/lib/            # API contract, query keys, formatting, analytics, grouping, types, platform-authoring helpers
├── src/hooks/          # TanStack Query hooks wrapping lib/api modules
├── src/pages/          # dashboard, extensions, finance workspace, Memory, Scheduled Tasks, and agent-platform routes
├── src/components/     # layout shell, theme, shared UI, cross-route dialogs, platform-authoring widgets, templates, portfolio UI, shadcn primitives
├── src/styles/         # fonts, theme tokens, and global CSS entrypoints; covered here
├── src/test/           # Vitest jsdom setup; covered here
├── e2e/                # Playwright route-family and shell-regression coverage
└── scripts/            # Playwright backend/frontend startup helpers; covered here
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App bootstrap | `src/App.tsx`, `src/routes.ts`, `src/routes.metadata.ts`, `src/extensions/runtime-helpers.ts`, `src/components/layout.tsx` | query client, router provider, metadata-driven shell/nav rendering, extension route assembly, theme toggle, and sidebar navigation |
| Extension runtime and state | `src/extensions/AGENTS.md`, `src/pages/extensions/AGENTS.md`, `src/extensions/runtime.tsx`, `src/extensions/runtime-helpers.ts`, `src/hooks/use-extensions.ts` | bundled frontend extensions, finance route/nav/tool filtering, and `/extensions` state UI |
| Shared API/state logic | `src/lib/AGENTS.md`, `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, `src/lib/platform-authoring/AGENTS.md`, `src/hooks/AGENTS.md` | typed fetch, query keys, wire contracts, platform-authoring helpers, and TanStack Query wrappers |
| Shared route shells and UI state | `src/components/shared/AGENTS.md`, `src/hooks/AGENTS.md` | inventory/workspace/split-inspector shells, resource chrome, and reusable cards/table/filter/selection/inspector state helpers |
| Portfolio routes | `src/pages/portfolios/AGENTS.md`, `src/components/portfolios/AGENTS.md` | list/detail workspace, balances, positions, trades |
| Template routes | `src/pages/templates/AGENTS.md`, `src/components/templates/AGENTS.md`, `src/hooks/use-templates.ts`, `src/lib/api/templates.ts` | CRUD, runtime inputs, placeholder tree, inline preview compile |
| Report routes | `src/pages/reports/AGENTS.md`, `src/hooks/use-reports.ts`, `src/lib/api/reports.ts`, `src/lib/report-grouping.ts` | generate from template, upload markdown, group/search, edit/download/delete |
| Agent-platform routes | `src/pages/workflow-packages/AGENTS.md`, `src/pages/scheduled-tasks/AGENTS.md`, `src/pages/model-connections/AGENTS.md`, `src/pages/memory/AGENTS.md`, `src/pages/runs/AGENTS.md` | Workflow Packages, Scheduled Tasks, Model Connections, Memory, and Runs, including schedule fire history, explicit-scope memory access, backend-owned run progress/queue payloads, and current rerun/fork readiness |
| Shared components | `src/components/AGENTS.md`, `src/components/platform-authoring/AGENTS.md`, `src/components/forms/*.tsx` | layout shell, theme, shared UI, cross-route dialogs, platform-authoring widgets, portfolio feature folders |
| UI primitives | `src/components/ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |
| Unit test setup | `vite.config.ts`, `src/test/setup.ts` | jsdom config plus browser API mocks |
| E2E flow setup | `playwright.config.ts`, `scripts/start-playwright-*.mjs` | backend `8001`, frontend `4173` |

## CONVENTIONS
- Routing stays flat under `Layout`; feature depth lives inside components and hooks, not in nested route trees.
- `src/routes.ts` is the route source of truth, with Finance Workspace route entries assembled from `src/extensions/runtime-helpers.ts`; `src/components/layout.tsx` renders the shell nav plus metadata-backed breadcrumbs.
- Server data flows through `src/lib/api*.ts` and `src/hooks/*`; routed screens should not call `fetch` directly.
- Keep React render logic pure; use effects only for external synchronization, not derived state or local data transforms.
- Browser-exposed env access goes through `import.meta.env`, and only `VITE_`-prefixed variables may reach frontend code.
- Use the `@` alias for `src/` imports instead of long relative paths.
- Mutation-heavy screens use Sonner toasts for success/error feedback and shadcn/ui primitives for dialogs/forms.
- `src/routes.metadata.ts` is the contract for route archetype, breadcrumb, sidebar ownership, shell mode, width mode, and visible state variants; `Layout` consumes that metadata instead of page-local chrome rules.
- Shared inventory/workspace/split-inspector shells plus the route-state hooks in `src/hooks/` are the default way to compose page chrome; do not fork cards/table/filter/selection/inspector scaffolding per route.
- Template preview and report generation both support runtime-input maps built from shared row helpers in `src/lib/runtime-inputs.ts`.
- Report flows are slug-addressed, use `use-reports.ts` for server state, and rely on `downloadReportUrl()` for native markdown downloads.
- Report inventory grouping/search/sort logic lives in `src/lib/report-grouping.ts`; the route composes that derived view state instead of re-implementing grouping inline.
- `GenerateReportDialog` is the shared surface for parameterized report creation from both the template editor and the report list.
- Workflow package editors are authoring-only YAML-manifest editors with local package-resource editing, backend validation, package secret bindings, import, and export. Launch, preflight gating, runtime parameters, saved inputs, and create-run state belong to the dedicated `/workflow-packages/:packageId/run` page labeled `Launch Workflow Package`.
- Agent-platform pages use dedicated hooks and route params to keep package CRUD, Scheduled Task automation, extension-filtered global Tools reads for package authoring, global Model Connections, explicit-scope Memory reads, backend-provided run progress/queue/readiness payloads, and Run inspection inside the routed page layer.
- Scheduled Task screens are platform-owned. Keep structured recurrence, scheduled input preview, fire history, archive/read-only behavior, and run-now links aligned with `use-scheduled-tasks.ts` and `queryKeys.platform.schedules`.
- `useExtensions()` drives Finance Workspace route/nav visibility, `/extensions` state UI, and tool filtering for package capability profiles.
- The `/extensions` page is a system state surface only; render only the backend contract (`key`, `label`, `enabled`) and keep marketplace/install/remove behavior out of phase 1.
- Model connection editors keep credentials write-only in the UI: blank edit submissions preserve the stored key, and inline connection tests run against the persisted backend connection only after save.
- This parent guide owns `src/styles/`, `src/test/`, and `scripts/` because those folders are still small. Split them back out only if they gain independent ownership or materially different rules.
- `src/styles/` owns global Tailwind/theme entrypoints only; keep one-off layout and feature styling in components instead of growing the global layer.
- `src/test/setup.ts` owns global jsdom/browser shims only; route-specific mocks, network mocks, and feature data factories stay with the owning tests.
- For ordinary removal-only validation, prefer manual confirmation over adding dedicated “proves not” UI tests; keep absence assertions only when the missing surface is itself a shipped contract or guardrail.
- Theme state lives in `src/components/theme-provider.tsx`; components should consume the existing context instead of inventing new color-mode state.
- Query keys normalize ids as strings, symbol lists as trimmed/deduplicated/sorted arrays where relevant, and portfolio, template, report, Memory, and agent-platform caches under dedicated namespaces.

## ANTI-PATTERNS
- Do not hard-code API URLs or call `fetch` directly from routed screens.
- Do not invent ad-hoc query keys or parse decimal strings in pages when shared helpers already exist.
- Do not put feature-heavy routed screens in `src/components/ui/`.
- Do not change API modules or shared wire types in isolation; update `src/lib/api/AGENTS.md`, `src/lib/types/AGENTS.md`, and the calling hooks together.
- Do not change template route, placeholder, or query-key shapes without updating hooks, types, and tests together.
- Do not change runtime-input row behavior, `inputs.*` expectations, or generation-dialog wiring without updating the editor, shared dialog, hooks, and backend compile contract together.
- Do not change report route, slug, upload/download, or query-key shapes without updating hooks, types, and tests together.
- Do not add dead routes or unused API modules without wiring them into the actual router and tests.
- Do not hard-code Finance Workspace visibility outside `src/extensions/runtime.tsx`, `src/extensions/runtime-helpers.ts`, and `use-extensions.ts`.
- Do not treat deleted route-family files as live route ownership or as a shortcut for new package-first UI.
- Do not document removed `/skills`, `/studio`, `/tryout`, `/orchestration`, `/backtests`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` routes as live surfaces.
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
- Current Vitest coverage spans `src/lib/` helpers plus targeted agent-platform, shared route-shell, inventory-state, template-editor, and layout pages.
- `src/styles/fonts.css` is empty/unreferenced; theme tokens live in `src/styles/theme.css` and Tailwind import/source control lives in `src/styles/tailwind.css`.
- The live router exposes dashboard, extension-gated portfolio/template/report routes, `/extensions`, Workflow Packages, Scheduled Tasks, Model Connections, `/memory`, and Runs; removed route families are guarded in `src/routes.test.tsx`.
