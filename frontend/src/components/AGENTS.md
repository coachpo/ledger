# FRONTEND COMPONENTS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers shared components, feature-specific components, and UI primitives in `src/components/`.

## OVERVIEW
`src/components/` contains the layout shell, theme system, shared component library, small cross-route form/dialog surfaces, platform-authoring widgets, template-editor support components, portfolio-specific UI folders, and shadcn/ui primitives. Routed page components live in `src/pages/` and map to routes in `src/routes.ts`, including extension-aware finance routes, the `/extensions` system route, and the current agent-platform routes.

Extension model: statically resident extension runtime nav groups and extension state.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## STRUCTURE
```text
src/components/
├── layout.tsx              # sidebar shell, breadcrumbs, route framing
├── theme-provider.tsx      # localStorage + system theme sync
├── theme-toggle.tsx        # header control for light/dark/system
├── theme.ts                # theme context types
├── shared/                 # reusable components across features
├── forms/                  # small cross-feature dialog/form helpers for templates, reports, portfolios, and model-connection secrets; covered here
├── templates/              # template-editor support components and placeholder/runtime-input UI
│   └── AGENTS.md
├── portfolios/             # portfolio feature-specific components
│   └── AGENTS.md
└── ui/                     # shadcn/ui primitives and helpers
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App shell / navigation | `layout.tsx`, `shared/error-boundary.tsx` | sidebar shell, metadata-driven shell/width framing, and route-safe fallback UI |
| Theme behavior | `theme-provider.tsx`, `theme-toggle.tsx`, `theme.ts` | persisted theme state and system-sync logic |
| Shared components | `shared/AGENTS.md` | reusable inventory/workspace shells, resource chrome, evidence helpers, tables, metrics, and field schemas |
| Cross-route dialogs and form helpers | `forms/portfolio-form-dialog.tsx`, `forms/generate-report-dialog.tsx`, `forms/secret-input.tsx` | small shared dialogs and write-only secret input UI |
| Platform authoring widgets | `platform-authoring/AGENTS.md` | schema composer, generated form, workflow builder, refs, inspectors |
| Template-editor support UI | `templates/AGENTS.md` | placeholder reference and runtime-input surfaces used by template routes |
| Portfolio feature UI | `portfolios/AGENTS.md` | sections, dialogs, trading form, feature-specific logic |
| Pure UI primitives | `ui/AGENTS.md` | shadcn/ui wrappers, sidebar primitives, variant helpers |

## CHILD DOCS
- `shared/AGENTS.md` — reusable inventory/workspace shells, resource chrome, evidence helpers, and schema rules
- `platform-authoring/AGENTS.md` — schema composer, generated form, workflow builder, refs, and inspectors
- `templates/AGENTS.md` — template-editor support components such as placeholder reference and runtime-input sections
- `portfolios/AGENTS.md` — portfolio feature sections, dialogs, and trades UI
- `ui/AGENTS.md` — presentational shadcn/ui wrappers, sidebar context, and shared style helpers

## CONVENTIONS
- Routed page components live in `src/pages/` and are thin route-layer components.
- Shared components in `shared/` are reusable across multiple features and should not contain portfolio-specific request logic.
- `shared/` is where the app keeps reusable inventory/workspace shells, resource chrome, data tables, metric cards, field schemas, and error boundaries; if a component only makes sense inside one feature route, keep it out of this folder.
- `forms/` is reserved for small cross-feature form surfaces such as portfolio creation/editing, shared report-generation dialogs reused by template/report routes, and write-only secret inputs used by model-connection flows.
- Form/dialog components accept data and callbacks from parents; they should not own navigation, toasts, hooks, or direct API calls.
- `platform-authoring/` is reserved for reusable agent-platform authoring widgets driven by `src/lib/platform-authoring/**`.
- `templates/` is reserved for template-editor support widgets such as placeholder browsing and runtime-input row controls.
- Feature-specific components in `portfolios/` own their domain logic and should not be reused outside that feature without a clear abstraction.
- Preserved product and agent-platform routes stay page-centric and reuse shared components; platform-authoring widgets are the exception because schema/value/ref/workflow UIs are shared across package-local agents, output schemas, capability profiles, MCP configs, and workflow graphs.
- `Layout` consumes route metadata plus extension runtime nav groups/state; shell mode, width mode, breadcrumbs, and sidebar composition belong there, not in leaf pages or sidebar primitives.
- Shared route-shell patterns such as inventory stacks, workspace shells, and split inspectors belong in `shared/`, not in `ui/` or copied page-local wrappers.
- Shared field schemas in `shared/form-schemas.ts` should stay aligned with the current routed forms that consume them.
- Theme state lives in `theme-provider.tsx`; leaf components should consume the existing context instead of creating new theme state.
- `ui/` stays presentational; application state and request logic should stay in pages, shared, forms, or feature folders.

## ANTI-PATTERNS
- Do not put business rules or raw request code in `ui/` components.
- Do not put feature-specific logic in `shared/` components.
- Do not duplicate portfolio feature rules in shared components when the portfolio folder already owns them.
- Do not move feature-rich components into `ui/` just because they render cards or forms.
- Do not create one-off form helpers in feature folders when they should live in `forms/` or a shared dialog component.
- Do not let form/dialog helpers own navigation, toasts, hooks, or API calls when the parent route should supply that behavior.
- Do not move template-editor-only support widgets into `shared/` just because they render generic inputs or lists.
- Do not hide current route ownership, route metadata, or shell framing inside generic UI primitives.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- `Layout` switches between scroll and full-height outlet treatment from route metadata, not hard-coded feature checks; template editor, workflow package editor/import/launch, run detail, and model-connection editor routes all rely on that contract.
- `Layout` renders the current sidebar entries plus metadata-backed breadcrumb labels, shell mode, width mode, and routed main framing for dashboard, extension-gated finance routes, `/extensions`, and agent-platform routes.
- `layout.tsx` owns route labels and nav composition; `ui/sidebar.tsx` and `ui/sidebar-context.ts` stay generic primitives.
- Page components stay thin; the real complexity lives in hooks, shared components, forms, and feature folders.
