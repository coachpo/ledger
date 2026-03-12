# Frontend Shadcn Replacement Audit And Plan

## Goal

Audit the current `frontend/` implementation, identify every meaningful UI/controller/pattern surface, map them to source-backed shadcn candidates, and define a phased replacement plan that preserves existing business logic while upgrading feature-level composition.

## Executive Read

- The app already uses a local shadcn-compatible primitive layer in `frontend/src/components/ui/`; this is not a greenfield shadcn adoption.
- The best migration target is feature composition, not a base-primitive rewrite.
- Highest leverage surfaces are the custom workspace shell, portfolio register/data tables, dialog/form stack, and the two stock-analysis screens.
- Most business logic lives outside the visual layer and should be preserved as-is: `api.ts`, `query-keys.ts`, `portfolio-analytics.ts`, `workspace.ts`, `use-portfolio-workspace-data.ts`, `use-user-preferences.ts`, `use-keyboard-shortcuts.ts`.
- `shadcn.io` is useful for patterns and blocks, but it is community-run and not the official registry; copy ideas and adapt imports/styles instead of pasting blindly.
- Immediate migration should stay narrow: baseline the current UI, add only missing shell/form/navigation primitives first, and defer advanced data-table, pagination, empty-state, and calendar upgrades until shared patterns are proven.

## Current Codebase Inventory

### Top-Level `frontend/src`

| Path | Type | Role |
|---|---|---|
| `frontend/src/main.tsx` | entry | React mount point |
| `frontend/src/App.tsx` | entry/controller | Provider stack, router tree, route registration |
| `frontend/src/index.css` | theme/tokens | Tailwind imports, fonts, CSS variables, light/dark theme tokens |
| `frontend/src/assets/react.svg` | asset | Default template asset; not product UI |
| `frontend/src/components/` | directory | Feature/UI/theme components |
| `frontend/src/hooks/` | directory | reusable controller hooks |
| `frontend/src/lib/` | directory | API, cache, analytics, formatting, helpers |
| `frontend/src/test/setup.ts` | test infra | Vitest setup |

### Routed Pages And Shell Surfaces

`frontend/src/App.tsx` defines the route tree below:

| Route / Surface | File | Role |
|---|---|---|
| app frame | `frontend/src/components/portfolios/app-frame.tsx` | top-level shell, sidebar, app header context, outer outlet |
| `/portfolios` | `frontend/src/components/portfolios/portfolio-list-page.tsx` | portfolio register, selection, batch delete |
| `/stock-analysis/inputs` | `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` | shared LLM/template/admin inputs |
| `/portfolios/:portfolioId` | `frontend/src/components/portfolios/portfolio-workspace-layout.tsx` | portfolio workspace shell and outlet context |
| `/overview` | `frontend/src/components/portfolios/portfolio-overview-page.tsx` | balances, positions, CSV import, metrics |
| `/trades/new` | `frontend/src/components/portfolios/portfolio-trade-page.tsx` | trade entry wrapper page |
| `/transactions` | `frontend/src/components/portfolios/portfolio-history-page.tsx` | grouped transaction history |
| `/analysis` | `frontend/src/components/portfolios/portfolio-analysis-page.tsx` | P&L, allocation, historical analysis |
| `/stock-analysis` | `frontend/src/components/portfolios/stock-analysis-workspace.tsx` | conversation/run/version workspace |
| `/assets/:symbol` | `frontend/src/components/portfolios/asset-detail-page.tsx` | symbol drilldown with chart/history |

### Portfolio Feature Components

| File | Exported Surface | Role |
|---|---|---|
| `frontend/src/components/portfolios/app-shell-layout.ts` | `APP_SHELL_SIDEBAR_WIDTH`, `APP_SHELL_CONTAINER_CLASS_NAME`, `APP_SHELL_MAIN_CLASS_NAME` | shell sizing/layout constants |
| `frontend/src/components/portfolios/portfolio-navigation.ts` | `PortfolioWorkspaceNavigationItem`, `portfolioWorkspaceNavigationItems` | workspace nav model |
| `frontend/src/components/portfolios/model.ts` | `portfolioCreateSchema`, `balanceSchema`, `positionCreateSchema`, `tradingOperationSchema`, `BASE_CURRENCY_OPTIONS` | Zod schema/controller model layer |
| `frontend/src/components/portfolios/use-portfolio-workspace-data.ts` | `usePortfolioWorkspaceData` | portfolio query/orchestration controller |
| `frontend/src/components/portfolios/shared.tsx` | `MetricCard`, `RowActionMenu`, `StatusCallout`, `EmptyState`, `FieldErrorText`, `normalizeOptionalText`, `formatSignedCurrency`, `isNotFoundError` | reusable feature UI and helpers |
| `frontend/src/components/portfolios/dialogs.tsx` | `PortfolioFormDialog`, `BalanceFormDialog`, `PositionFormDialog`, `CsvImportDialog`, `ConfirmDeleteDialog` | modal stack for CRUD/import/destructive flows |
| `frontend/src/components/portfolios/trading-operation-form.tsx` | `TradingOperationForm` | conditional trading form/controller UI |
| `frontend/src/components/portfolios/portfolio-workspace-layout.tsx` | `PortfolioWorkspaceContextValue`, `usePortfolioWorkspace`, `PortfolioWorkspaceLayout` | nested route shell plus workspace context |
| `frontend/src/components/portfolios/app-frame.tsx` | `AppFrame` | global shell |
| `frontend/src/components/portfolios/portfolio-list-page.tsx` | `PortfolioListPage` | portfolio register page |
| `frontend/src/components/portfolios/portfolio-overview-page.tsx` | `PortfolioOverviewPage` | overview page |
| `frontend/src/components/portfolios/portfolio-trade-page.tsx` | `PortfolioTradePage` | trade page wrapper |
| `frontend/src/components/portfolios/portfolio-history-page.tsx` | `PortfolioHistoryPage` | history page |
| `frontend/src/components/portfolios/portfolio-analysis-page.tsx` | `PortfolioAnalysisPage` | analysis page |
| `frontend/src/components/portfolios/asset-detail-page.tsx` | `AssetDetailPage` | asset detail page |
| `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` | `StockAnalysisInputsPage` | stock-analysis admin/settings page |
| `frontend/src/components/portfolios/stock-analysis-workspace.tsx` | `StockAnalysisWorkspace` | stock-analysis workspace page |

### Theme Components

| File | Exported Surface | Role |
|---|---|---|
| `frontend/src/components/theme/theme-provider.tsx` | `ThemeProvider` | next-themes wrapper with preference guard |
| `frontend/src/components/theme/theme-toggle.tsx` | `ThemeToggle` | theme switcher dropdown |

### Controller-Like Hooks And Libraries

| File | Surface | Why It Matters |
|---|---|---|
| `frontend/src/hooks/use-keyboard-shortcuts.ts` | keyboard navigation hook | owns `Alt+1..5`, `t`, and a placeholder `Cmd/Ctrl+K` command action |
| `frontend/src/hooks/use-user-preferences.ts` | persisted UI preferences hook | controls default analysis tabs and saved preferences |
| `frontend/src/lib/api.ts` | API contract layer | all backend DTOs and request helpers |
| `frontend/src/lib/query-keys.ts` | query key factory + invalidator | shared cache key discipline |
| `frontend/src/lib/portfolio-analytics.ts` | analytics engine | dashboard metrics, allocation, P&L, historical grouping |
| `frontend/src/lib/workspace.ts` | sorting helpers | consistent register/workspace ordering |
| `frontend/src/lib/format.ts` | formatting + error extraction | display and API error normalization |
| `frontend/src/lib/utils.ts` | `cn()` | class merging utility |

### Existing UI Primitive Layer

These are already local shadcn-style wrappers and should be treated as keep-or-refresh components, not first-pass replacement candidates.

| File | Exports |
|---|---|
| `frontend/src/components/ui/alert.tsx` | `Alert`, `AlertTitle`, `AlertDescription`, `AlertAction` |
| `frontend/src/components/ui/alert-dialog.tsx` | `AlertDialog`, `AlertDialogAction`, `AlertDialogCancel`, `AlertDialogContent`, `AlertDialogDescription`, `AlertDialogFooter`, `AlertDialogHeader`, `AlertDialogMedia`, `AlertDialogOverlay`, `AlertDialogPortal`, `AlertDialogTitle`, `AlertDialogTrigger` |
| `frontend/src/components/ui/badge.tsx` | `Badge`, `badgeVariants` |
| `frontend/src/components/ui/button.tsx` | `Button`, `buttonVariants` |
| `frontend/src/components/ui/card.tsx` | `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardAction`, `CardContent`, `CardFooter` |
| `frontend/src/components/ui/chart.tsx` | `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`, `ChartLegend`, `ChartLegendContent`, `ChartConfig` |
| `frontend/src/components/ui/checkbox.tsx` | `Checkbox` |
| `frontend/src/components/ui/collapsible.tsx` | `Collapsible`, `CollapsibleTrigger`, `CollapsibleContent` |
| `frontend/src/components/ui/dialog.tsx` | `Dialog`, `DialogTrigger`, `DialogPortal`, `DialogClose`, `DialogOverlay`, `DialogContent`, `DialogHeader`, `DialogFooter`, `DialogTitle`, `DialogDescription` |
| `frontend/src/components/ui/dropdown-menu.tsx` | `DropdownMenu`, `DropdownMenuPortal`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuGroup`, `DropdownMenuItem`, `DropdownMenuCheckboxItem`, `DropdownMenuRadioGroup`, `DropdownMenuRadioItem`, `DropdownMenuLabel`, `DropdownMenuSeparator`, `DropdownMenuShortcut`, `DropdownMenuSub`, `DropdownMenuSubTrigger`, `DropdownMenuSubContent` |
| `frontend/src/components/ui/input.tsx` | `Input` |
| `frontend/src/components/ui/label.tsx` | `Label` |
| `frontend/src/components/ui/scroll-area.tsx` | `ScrollArea`, `ScrollBar` |
| `frontend/src/components/ui/select.tsx` | `Select`, `SelectGroup`, `SelectValue`, `SelectTrigger`, `SelectContent`, `SelectLabel`, `SelectItem`, `SelectSeparator`, `SelectScrollUpButton`, `SelectScrollDownButton` |
| `frontend/src/components/ui/sheet.tsx` | `Sheet`, `SheetTrigger`, `SheetClose`, `SheetContent`, `SheetHeader`, `SheetFooter`, `SheetTitle`, `SheetDescription` |
| `frontend/src/components/ui/skeleton.tsx` | `Skeleton` |
| `frontend/src/components/ui/sonner.tsx` | `Toaster` |
| `frontend/src/components/ui/table.tsx` | `Table`, `TableHeader`, `TableBody`, `TableFooter`, `TableRow`, `TableHead`, `TableCell`, `TableCaption` |
| `frontend/src/components/ui/tabs.tsx` | `Tabs`, `TabsList`, `TabsTrigger`, `TabsContent`, `tabsListVariants` |
| `frontend/src/components/ui/textarea.tsx` | `Textarea` |
| `frontend/src/components/ui/tooltip.tsx` | `Tooltip`, `TooltipContent`, `TooltipProvider`, `TooltipTrigger` |

### Tests

| File | Scope |
|---|---|
| `frontend/src/components/portfolios/app-frame.test.tsx` | app shell coverage |
| `frontend/src/components/portfolios/portfolio-list-page.test.tsx` | portfolio register coverage |
| `frontend/src/hooks/use-user-preferences.test.ts` | persisted preference behavior |
| `frontend/src/lib/format.test.ts` | formatting helpers |
| `frontend/src/lib/portfolio-analytics.test.ts` | analytics layer |
| `frontend/src/lib/workspace.test.ts` | sorting/helpers |
| `frontend/src/test/setup.ts` | vitest setup |

## Current UI / Controller Patterns

### Routing And Provider Stack

- `frontend/src/App.tsx` composes `QueryClientProvider`, `ThemeProvider`, `TooltipProvider`, `BrowserRouter`, and `Toaster`.
- Nested routing is the core app architecture; portfolio workspace pages depend on `PortfolioWorkspaceLayout` outlet context.
- No auth/guard layer exists in the frontend route tree right now.

### Theme And Visual Tokens

- `frontend/src/index.css` already defines a mature token system with `--background`, `--foreground`, `--card`, `--primary`, `--chart-*`, `--sidebar-*`, and brand variables.
- Typography is intentional: Geist for UI plus Newsreader as display font.
- The app already supports light/dark themes and pre-applies theme state before mount.

### Forms

- Form logic is concentrated in `frontend/src/components/portfolios/dialogs.tsx` and `frontend/src/components/portfolios/trading-operation-form.tsx`.
- Direct evidence: 15 `useForm`/`Controller`/`zodResolver` matches across those 2 files.
- Current pattern is `react-hook-form` + `zodResolver` + `Controller` + hand-built label/error sections.
- Conditional business rules live in schemas and `TradingOperationForm`, not in UI wrappers.

### Queries And Mutations

- Query/mutation complexity is concentrated in stock-analysis screens.
- Direct evidence: 21 `useQuery`/`useMutation` matches across 5 files, with `stock-analysis-workspace.tsx` alone accounting for 11 and `stock-analysis-inputs-page.tsx` for 7.
- `use-portfolio-workspace-data.ts` is the central orchestration hook and should remain the backbone of workspace pages.

### Tables And Dense Data Views

- Direct evidence: 148 table-family matches across 5 files.
- `portfolio-list-page.tsx`, `portfolio-overview-page.tsx`, `portfolio-history-page.tsx`, and `dialogs.tsx` all lean on the local semantic `Table` primitive.
- Row actions currently come from `RowActionMenu` or custom action button groups instead of a reusable data-table abstraction.

### Charts And Analytics

- Direct evidence: 22 chart-family matches across `portfolio-analysis-page.tsx`, `asset-detail-page.tsx`, and `components/ui/chart.tsx`.
- The app already uses a shadcn-style `ChartContainer` wrapper; charts are a keep-and-polish area, not a replace-from-scratch area.

### Dialogs, Alerts, Sheets

- Direct evidence: 91 dialog/sheet matches across 5 files.
- `dialogs.tsx` and `stock-analysis-inputs-page.tsx` are the heaviest consumers.
- Current destructive flows already use `AlertDialog`; edit/create flows already use `Dialog`; `Sheet` exists locally but is not yet a first-class feature pattern.

### Reusable Feature Abstractions

- Direct evidence: 145 `StatusCallout` / `EmptyState` / `MetricCard` / `RowActionMenu` matches across 12 files.
- `shared.tsx` is the current feature design-system layer on top of primitives.
- These abstractions are the best seam for migration because they centralize repeated feature UI without touching controller logic.

### Visual Language

- Display typography is heavily reused: 50 display-font matches across 13 files.
- Rounded/pill styling is pervasive: 108 rounded-full/custom-radius matches across 14 files.
- The visual system is already coherent, so the goal is to tighten consistency and ergonomics, not change brand direction.

## What Should And Should Not Be Replaced

### Keep (Foundation Is Already Good)

- `frontend/src/components/ui/*` as the primary primitive layer, with selective refresh only when new registry components are needed.
- `frontend/src/lib/*` and controller hooks.
- `frontend/src/components/portfolios/use-portfolio-workspace-data.ts` and analytics/sorting logic.
- `frontend/src/index.css` token system and theme model.
- `frontend/src/components/ui/chart.tsx` and existing Recharts integration.

### Replace Or Refactor (Highest ROI)

- Custom app/workspace shell composition in `app-frame.tsx` and `portfolio-workspace-layout.tsx`.
- Portfolio register/table experiences in `portfolio-list-page.tsx` and parts of `portfolio-overview-page.tsx`.
- Form field layout and mobile behavior in `dialogs.tsx` and `trading-operation-form.tsx`.
- Repeated empty-state presentation in `shared.tsx` and heavy feature pages.
- Stock-analysis screen composition, especially oversized cards/list/detail panes.

### Add Rather Than Replace

- Immediate candidates: `sidebar`, `breadcrumb`, `command`, `form`, `field`
- Phase-later candidates: `drawer`, `empty`, `pagination`, `calendar`
- Reference-only patterns for later consideration: `data-table-advanced-4`, `dashboard-01`, `sidebar-16`, date-range picker patterns

Immediate scaffold command already supported by current `components.json`:

```bash
npx shadcn@latest add @shadcn/sidebar @shadcn/breadcrumb @shadcn/command @shadcn/form @shadcn/field
```

Deferred add command, only after earlier phases stabilize:

```bash
npx shadcn@latest add @shadcn/drawer @shadcn/empty @shadcn/pagination @shadcn/calendar
```

## Source-Backed Replacement Candidates

### Source Reliability Notes

- Official registry/docs: `ui.shadcn.com` and `@shadcn/*` registry items.
- Community patterns/blocks: `shadcn.io`; useful for composition ideas, not guaranteed drop-in compatibility.
- Current repo uses `components.json` with `style: radix-nova`, so community examples that assume `new-york-v4` need adaptation.

### Replacement Matrix

| Current Surface | Current Pattern | Recommended Target | Why | Sources |
|---|---|---|---|---|
| `frontend/src/components/portfolios/app-frame.tsx` | custom sidebar/register shell | `@shadcn/sidebar` plus `sidebar-16`/`dashboard-01` composition ideas | the shell is bespoke and dense; sidebar primitives provide better collapse/mobile semantics and a cleaner header/search slot | official registry `@shadcn/sidebar`; community block `https://www.shadcn.io/template/category/dashboard`; example `sidebar-16`; block `dashboard-01` |
| `frontend/src/components/portfolios/portfolio-workspace-layout.tsx` | custom workspace header with manual nav context | `breadcrumb` + refreshed sidebar/header composition | workspace context is strong, but page orientation can improve with breadcrumb/header patterns | `https://www.shadcn.io/ui/breadcrumb`; `breadcrumb-demo`; `sidebar-16` site-header pattern |
| `frontend/src/hooks/use-keyboard-shortcuts.ts` | keyboard nav with placeholder `Cmd/Ctrl+K` | `command` / `command-dialog` | there is already an explicit placeholder; command palette is the cleanest missing navigation feature | `https://www.shadcn.io/ui/command`; registry example `command-dialog` |
| `frontend/src/components/portfolios/portfolio-list-page.tsx` | semantic table + custom selection + batch actions | keep semantic `Table` first; consider data-table/pagination only as a later enhancement | register management is important, but advanced table state should not be bundled into the first migration wave | `https://www.shadcn.io/ui/data-table`; `https://www.shadcn.io/patterns/data-table-advanced-4`; `https://www.shadcn.io/ui/pagination`; `https://www.shadcn.io/ui/table`; `https://www.shadcn.io/ui/skeleton`; registry `empty` |
| `frontend/src/components/portfolios/portfolio-overview-page.tsx` | mixed dashboard cards, collapsibles, tables, dialogs | keep cards/charts and semantic tables; defer `empty`, advanced table, and pagination changes until later | overview mixes dense data editing and repeated empty states; first pass should reduce composition complexity without changing data semantics | `https://www.shadcn.io/ui/table`; `https://www.shadcn.io/ui/data-table`; `https://www.shadcn.io/ui/drawer`; `https://www.shadcn.io/ui/sheet`; registry `empty` |
| `frontend/src/components/portfolios/portfolio-history-page.tsx` | collapsible month groups + table | keep collapsible grouping and semantic `Table`; defer pagination/empty standardization | current structure is conceptually good; early migration should avoid introducing new list state | `https://www.shadcn.io/ui/pagination`; `https://www.shadcn.io/ui/skeleton`; registry `empty` |
| `frontend/src/components/portfolios/dialogs.tsx` | large hand-assembled dialog forms | official `form` plus responsive drawer/dialog pattern | field layout and mobile UX are the main gaps; controller logic is already sound | `https://www.shadcn.io/ui/form`; registry example `form-rhf-complex`; registry example `drawer-dialog`; `https://www.shadcn.io/ui/dialog`; `https://www.shadcn.io/ui/drawer`; `https://www.shadcn.io/ui/sheet` |
| `frontend/src/components/portfolios/trading-operation-form.tsx` | conditional RHF form with native datetime-local | `form` + `field` + optional `calendar/date-picker` later | first improve structure and validation UI; only replace date input if UX needs justify new dependency | `https://www.shadcn.io/ui/form`; registry example `form-rhf-complex`; `https://www.shadcn.io/ui/calendar`; `https://www.shadcn.io/patterns/date-picker-standard-1` |
| `frontend/src/components/portfolios/shared.tsx` | homegrown feature design-system | keep `StatusCallout` and `EmptyState` in the first wave; revisit `@shadcn/empty` later if consistency still lags | shared abstractions are the right migration seam, but they are stable enough to defer | registry `empty`; `https://www.shadcn.io/patterns/data-table-advanced-4`; `https://www.shadcn.io/ui/alert` |
| `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` | giant settings/admin page with dialogs and tabs | `form`, `sheet with tabs`, drawer/dialog responsiveness, better empty/skeleton consistency | this page is one of the heaviest UI hotspots and will benefit from stronger composition primitives | `https://www.shadcn.io/ui/form`; `https://www.shadcn.io/patterns/sheet-multi-section-2`; `https://www.shadcn.io/ui/dialog`; `https://www.shadcn.io/ui/drawer`; `https://www.shadcn.io/ui/tabs`; registry `empty` |
| `frontend/src/components/portfolios/stock-analysis-workspace.tsx` | oversized custom workspace with conversation and detail panes | sidebar-like sectional layout, command navigation, standardized empty/skeleton, selective sheet/drawer detail views | it is query-heavy and should be visually decomposed before any style transplant | `dashboard-01`; `sidebar-16`; `https://www.shadcn.io/ui/command`; `https://www.shadcn.io/ui/skeleton`; registry `empty`; `https://www.shadcn.io/ui/drawer`; `https://www.shadcn.io/ui/sheet` |
| `frontend/src/components/portfolios/portfolio-analysis-page.tsx` and `asset-detail-page.tsx` | existing chart card compositions | keep existing chart wrapper; borrow `dashboard-01` chart card interactions | chart infrastructure already matches shadcn style; only higher-level presentation should change | `dashboard-01`; `https://www.shadcn.io/ui/tabs`; `https://www.shadcn.io/charts` |

## Dependency And Compatibility Notes

### Already Present In `frontend/package.json`

- `@tanstack/react-table`
- `react-hook-form`
- `zod`
- `recharts`
- `sonner`
- `vaul`
- `next-themes`
- `class-variance-authority`
- `tw-animate-css`

### Likely Added By New Registry Components

- `cmdk` if `command` is introduced.
- `react-day-picker` if `calendar` / `date-picker` patterns are adopted.

### Compatibility Constraints

- Preserve Vite/React assumptions; do not import Next-only helpers from community examples.
- Adapt community examples that reference `new-york-v4` registry paths to the repo's local aliases.
- Preserve `radix-nova` style choices in `components.json` and existing CSS variables in `frontend/src/index.css`.

## Recommended Final Implementation Plan

### Phase 0: Baseline And Scaffolding

1. Capture a UI baseline for `app-frame.tsx`, `portfolio-workspace-layout.tsx`, dialog flows, table-heavy pages, and stock-analysis screens using existing Playwright coverage plus targeted screenshots.
2. Freeze `frontend/src/components/ui/*` as keep-by-default.
3. Add missing official components: `sidebar`, `breadcrumb`, `command`, `form`, `field`.
4. Do not touch page layouts yet.
5. Confirm registry-generated code aligns with `radix-nova`, `@/` aliases, and current tokens.

### Phase 1: Navigation And Shell Modernization

1. Refactor `frontend/src/components/portfolios/app-frame.tsx` to adopt official `sidebar` primitives while preserving current route structure and portfolio navigation logic.
2. Add breadcrumb/header support in `frontend/src/components/portfolios/portfolio-workspace-layout.tsx`.
3. Implement a `CommandDialog` launched from the existing `Cmd/Ctrl+K` placeholder in `frontend/src/hooks/use-keyboard-shortcuts.ts`.
4. Keep `portfolioWorkspaceNavigationItems` as the source of truth.

### Phase 2: Dialog And Form Standardization

1. Refactor `frontend/src/components/portfolios/dialogs.tsx` into smaller UI sections before applying shadcn `form`/`field` conventions.
2. Refactor `frontend/src/components/portfolios/trading-operation-form.tsx` into smaller UI sections using the same field/message structure.
3. Leave schemas, submit handlers, toasts, and invalidation behavior untouched.
4. Introduce responsive drawer/dialog behavior only after the forms are structurally decomposed and verified.

### Phase 3: Table, Empty, And Pagination Upgrade

1. Refresh `frontend/src/components/portfolios/portfolio-list-page.tsx`, `portfolio-overview-page.tsx`, and `portfolio-history-page.tsx` after shell/forms stabilize.
2. Keep the semantic `Table` primitive and current table semantics in the initial table pass.
3. Standardize action-menu affordances and loading states without introducing advanced data-table or pagination state yet.
4. Re-evaluate `@shadcn/empty`, `@shadcn/pagination`, and advanced table patterns only after those pages have stabilized visually.

### Phase 4: Dashboard And Analytics Polish

1. Refresh `frontend/src/components/portfolios/portfolio-overview-page.tsx`, `portfolio-analysis-page.tsx`, and `asset-detail-page.tsx` using higher-level dashboard/card composition patterns.
2. Keep `ChartContainer` and chart business logic.
3. Optionally add range pickers only where native date/datetime inputs are insufficient.
4. Treat `dashboard-01`, `sidebar-16`, and chart blocks as composition references, not copy-paste targets.

### Phase 5: Stock Analysis Decomposition

1. Split `frontend/src/components/portfolios/stock-analysis-inputs-page.tsx` into smaller subcomponents before meaningful visual replacement.
2. Split `frontend/src/components/portfolios/stock-analysis-workspace.tsx` into pane-level sections (settings, conversation list, selected conversation, runs, versions).
3. Apply sidebar/command/empty/skeleton/sheet/drawer patterns only after the files are decomposed.
4. Keep query trees and mutation orchestration stable.

### Phase 6: Deferred Enhancements

1. Only after earlier phases are stable, consider `@shadcn/empty`, `@shadcn/pagination`, `@shadcn/calendar`, and advanced data-table patterns.
2. Validate each deferred addition against actual UX pain before implementation.
3. Avoid introducing new selection, filtering, or date semantics purely for stylistic reasons.

## Risks And Guardrails

### Risks

- A big-bang rewrite would mix visual churn with controller churn and likely break routing/form flows.
- `shadcn.io` examples often assume Next.js and different registry styles.
- Stock-analysis pages are too large to safely restyle without first extracting subcomponents.
- `data-table` can add unnecessary complexity if used on every table indiscriminately.
- `calendar` / `date-picker` adds UX and timezone complexity that native inputs currently avoid.
- Thin component-level test coverage means visual regressions are a bigger near-term risk than controller regressions.

### Guardrails

- Never rewrite `frontend/src/lib/api.ts`, `query-keys.ts`, `portfolio-analytics.ts`, or `use-portfolio-workspace-data.ts` for visual reasons.
- Prefer replacing repeated feature abstractions (`EmptyState`, row actions, shell composition) before page internals.
- Use official shadcn registry components as the implementation base; use `shadcn.io` only for composition patterns.
- Preserve current toast/error/degraded-data behavior for quotes and stock-analysis responses.
- Use Playwright screenshots and current flows as the baseline before refactoring large surfaces.

## Acceptance Criteria For The Future Implementation

- Existing route structure remains unchanged.
- Pre-migration and post-migration screenshots remain visually equivalent for unchanged flows.
- Query/mutation behavior and invalidation semantics remain unchanged.
- Light/dark themes still use the current token system.
- `Cmd/Ctrl+K` opens a real command palette.
- Portfolio register retains current selection/delete behavior even before any advanced table work is considered.
- Dialog/form flows become mobile-appropriate without losing keyboard accessibility.
- Empty/loading states become more consistent, but may stay on local abstractions in early phases.
- `pnpm lint`, `pnpm test`, and `pnpm build` still pass after each phase.

## Suggested Implementation Order For Small PRs

1. Capture UI baseline screenshots/flows.
2. Add `sidebar`, `breadcrumb`, `command`, `form`, and `field` primitives.
3. Wire command palette from `use-keyboard-shortcuts.ts`.
4. Modernize app/workspace shell.
5. Refactor dialog stack and trading form structure.
6. Apply responsive drawer/dialog behavior only where proven necessary.
7. Refresh table-heavy pages while keeping semantic `Table`.
8. Polish overview/analysis/detail cards.
9. Decompose stock-analysis pages.
10. Apply final stock-analysis UI refactor.
11. Consider deferred `empty`/`pagination`/`calendar`/advanced-table upgrades.

## External References Used

### Official / Registry

- `@shadcn/sidebar`, `@shadcn/breadcrumb`, `@shadcn/command`, `@shadcn/form`, `@shadcn/field`, `@shadcn/empty`, `@shadcn/drawer`, `@shadcn/pagination`, `@shadcn/calendar`
- `ui.shadcn.com` guidance for migration and official component semantics

### Community / Pattern References

- `https://www.shadcn.io/`
- `https://www.shadcn.io/ui/dialog`
- `https://www.shadcn.io/ui/sheet`
- `https://www.shadcn.io/ui/data-table`
- `https://www.shadcn.io/ui/table`
- `https://www.shadcn.io/ui/command`
- `https://www.shadcn.io/ui/breadcrumb`
- `https://www.shadcn.io/ui/pagination`
- `https://www.shadcn.io/ui/calendar`
- `https://www.shadcn.io/ui/form`
- `https://www.shadcn.io/ui/skeleton`
- `https://www.shadcn.io/ui/drawer`
- `https://www.shadcn.io/ui/tabs`
- `https://www.shadcn.io/patterns/data-table-advanced-4`
- `https://www.shadcn.io/patterns/sheet-multi-section-2`
- `https://www.shadcn.io/patterns/date-picker-standard-1`
