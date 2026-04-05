# FRONTEND UI PRIMITIVES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/components/AGENTS.md`. This file covers `src/components/ui/`.

## OVERVIEW
`src/components/ui/` contains shadcn/ui-style primitives, shared variant helpers, sidebar shell primitives, and tiny UI-only utilities such as `cn()` and `useSidebar()`. Treat this folder as presentational infrastructure, not a feature layer.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Shared class merging | `utils.ts` | `cn()` wraps `clsx` + `tailwind-merge` |
| Button-like variants | `button-variants.ts`, `badge-variants.ts`, `toggle-variants.ts` | shared `cva()` recipes and token choices |
| Sidebar primitives | `sidebar.tsx`, `sidebar-context.ts` | provider/context, mobile sheet vs desktop inset, tooltip-ready menu buttons |
| Form controls | `input.tsx`, `textarea.tsx`, `select.tsx`, `checkbox.tsx`, `radio-group.tsx`, `switch.tsx` | presentational controls only |
| Overlay/menu wrappers | `dialog.tsx`, `sheet.tsx`, `dropdown-menu.tsx`, `context-menu.tsx`, `popover.tsx`, `tooltip.tsx`, `menubar.tsx`, `navigation-menu.tsx` | Radix-backed wrappers |
| Layout/display wrappers | `accordion.tsx`, `card.tsx`, `scroll-area.tsx`, `separator.tsx`, `table.tsx`, `tabs.tsx`, `chart.tsx`, `sidebar.tsx` | structural UI building blocks |

## CONVENTIONS
- Keep wrappers thin around Radix/shadcn behavior; Ledger-specific state belongs in pages or feature components.
- Reusable class recipes live in dedicated `*-variants.ts` files via `cva()` when tokens are shared across multiple wrappers.
- Use `cn()` from `utils.ts` for class composition instead of manual string concatenation.
- `sidebar.tsx` and `sidebar-context.ts` are generic primitives; route labels, nav items, breadcrumbs, and page metadata stay in `../layout.tsx`.
- `asChild`/`Slot` composition is allowed when callers need to supply links or buttons without losing primitive styling.
- Helpers such as `use-mobile.ts` stay UI-only and must not know about routes, API state, or domain-specific types.

## ANTI-PATTERNS
- Do not import hooks, API modules, or feature-specific business logic into this folder.
- Do not add toasts, navigation decisions, or request handling here.
- Do not fork `sidebar.tsx` with Ledger menu items; compose navigation from `../layout.tsx`.
- Do not bury reusable token sets inline when a dedicated `*-variants.ts` helper is already the pattern.
- Do not move portfolio, report, or template feature markup into `ui/` just because it renders cards, tables, or dialogs.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
pnpm build
```

## NOTES
- `sidebar.tsx` is the largest primitive file here; it handles mobile/desktop behavior, inset layout, and tooltip-ready menu buttons without owning app navigation.
- `SidebarProvider` and `useSidebar()` must stay paired; the context intentionally throws outside the provider to catch shell misuse early.
