# Frontend shadcn.io Replacement Plan

This document captures the verified replacement plan for the frontend under `frontend/src/`. The scope is planning only: scan the frontend surface, identify suitable proven `shadcn.io` matches, and classify each area as a replacement candidate, keep-as-is component, or explicit out-of-scope layer.

## A. Inventory Coverage

Every relevant area under `frontend/src/` falls into one of three buckets.

### Replacement / Pattern-Adoption Candidates

| Path | Category |
| --- | --- |
| `components/layout.tsx` | App shell |
| `components/portfolios/portfolio-positions-section.tsx` | Data table |
| `components/portfolios/portfolio-trades-section.tsx` | Data table |
| `components/portfolios/balance-form-dialog.tsx` | Simple form |
| `components/portfolios/portfolio-form-dialog.tsx` | Simple form |
| `components/portfolios/position-form-dialog.tsx` | Simple form |
| `components/snippet-form.tsx` | Simple form |
| `components/prompt-template-form.tsx` | Simple form |
| `components/portfolios/trading-operation-form.tsx` | Complex form |
| `components/llm-configs.tsx` | Complex form + list actions |
| `components/stock-analysis/run-builder-form.tsx` | Complex form |
| `components/stock-analysis/run-builder-mode-fields.tsx` | Complex form child |
| `components/stock-analysis/conversation-picker.tsx` | Combobox + create form |
| `components/responses-page.tsx` | Filter comboboxes |
| `components/snippets.tsx` | Card-list actions |
| `components/prompt-templates.tsx` | Card-list actions |
| `components/portfolios/portfolio-list-page.tsx` | Card-list actions |
| `components/dashboard.tsx` | Dashboard pattern polish |
| `components/portfolios/portfolio-detail-page.tsx` | Shared metric-card pattern |

### Keep-As-Is / No-Match Components

| Path | Reason |
| --- | --- |
| `components/ui/*` | Existing shadcn/ui primitive foundation |
| `components/error-boundary.tsx` | React error boundary, not a shadcn replacement target |
| `components/portfolios/confirm-delete-dialog.tsx` | Already a clean `AlertDialog` wrapper |
| `components/portfolios/portfolio-balances-section.tsx` | Low-count card grid is appropriate |
| `components/stock-analysis/prompt-preview-panel.tsx` | Domain-specific preview surface |
| `components/stock-analysis/run-status-display.tsx` | Domain-specific status/polling surface |
| `components/stock-analysis/run-builder-page.tsx` | Orchestrator page; children are the replacement targets |
| `components/snippet-create-page.tsx` | Thin page wrapper |
| `components/prompt-template-create-page.tsx` | Thin page wrapper |

### Scanned But Out of Replacement Scope

| Path | Reason |
| --- | --- |
| `main.tsx` | React root mount + CSS import |
| `App.tsx` | Provider/bootstrap composition; only indirectly touched by shell migration |
| `routes.ts` | Route table, not a UI replacement target |
| `hooks/*` | Data/query logic layer |
| `lib/*` | API, formatting, analytics, and query-key logic |
| `test/*` | Test infrastructure |

## B. Replacement Matrix

### App Shell

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/layout.tsx` | Custom desktop sidebar + mobile sheet navigation | `sidebar` pattern, using a proven block such as `sidebar-07` or similar inset/collapsible sidebar composition | Full | P1 | Adapt block structure to `react-router` `NavLink`, preserve seven destinations, move to `SidebarProvider` + `SidebarInset` + `SidebarTrigger` pattern |

### Data Tables

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/portfolios/portfolio-positions-section.tsx` | Manual positions table with edit/delete actions | `data-table-demo` pattern | Full | P0 | Install and use `@tanstack/react-table`; preserve existing value formatting and PnL color logic |
| `components/portfolios/portfolio-trades-section.tsx` | Manual trades table | `data-table-demo` pattern | Full | P0 | Add sorting/pagination while preserving existing operation description rendering |

### Card-List Actions

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/llm-configs.tsx` | Card list with bare icon actions | `dropdown-menu` pattern | Partial | P2 | Keep card layout, replace inline action buttons with menu actions |
| `components/snippets.tsx` | Collapsible card list with actions | `dropdown-menu` pattern | Partial | P3 | Keep collapsible presentation |
| `components/prompt-templates.tsx` | Card list with edit/delete actions | `dropdown-menu` pattern | Partial | P3 | Keep list layout |
| `components/portfolios/portfolio-list-page.tsx` | Portfolio cards with actions | `dropdown-menu` pattern | Partial | P3 | Keep cards, improve action affordance |

### Searchable Selection

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/responses-page.tsx` | Portfolio/conversation filter selects | `combobox-popover` pattern using `Command` + `Popover` | Partial | P3 | Replace only filter selects |
| `components/stock-analysis/conversation-picker.tsx` | Existing conversation select | `combobox-popover` pattern | Partial | P2 | Pair with separate create-form migration |

### Simple Forms

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/portfolios/balance-form-dialog.tsx` | Two-field dialog form | `form` + RHF input examples | Full | P1 | Best first migration target |
| `components/portfolios/portfolio-form-dialog.tsx` | Portfolio create/edit dialog | `form` + RHF input/select patterns | Full | P1 | Preserve base-currency select |
| `components/portfolios/position-form-dialog.tsx` | Position create/edit dialog | `form` + RHF input patterns | Full | P1 | Straightforward schema migration |
| `components/snippet-form.tsx` | Snippet form | RHF input + textarea patterns | Full | P1 | Shared by create/edit flows |
| `components/prompt-template-form.tsx` | Prompt-template form | RHF input + textarea patterns | Full | P1 | Similar to snippet form |

### Complex Forms

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/portfolios/trading-operation-form.tsx` | Conditional BUY/SELL/DIVIDEND/SPLIT form | RHF complex-form pattern | Full | P1 | Use a discriminated-union schema |
| `components/llm-configs.tsx` | Inline config form with slider, switch, conditional fields | RHF complex-form pattern | Full | P2 | Extract form from page before migrating |
| `components/stock-analysis/run-builder-form.tsx` | Large stateful run-builder form | RHF complex-form pattern | Partial | P2 | Use `watch()` to simplify preview derivation |
| `components/stock-analysis/run-builder-mode-fields.tsx` | Child conditional-field component | RHF-controlled textareas/fields | Full | P2 | Replace prop-heavy state plumbing with `control` |
| `components/stock-analysis/conversation-picker.tsx` | Inline create-conversation form | RHF input/select patterns | Full | P2 | Split from selection UI if needed |

### Dashboard / Shared Pattern Polish

| File | Current Role | shadcn.io Match | Scope | Priority | Notes |
| --- | --- | --- | --- | --- | --- |
| `components/dashboard.tsx` | Metric cards, summary layout, skeleton states | `dashboard-01` pattern inspiration + skeleton card patterns | Pattern-only | P3 | Adopt structure, not drag-and-drop/table extras |
| `components/portfolios/portfolio-detail-page.tsx` | Reuses inline metric-card pattern | Shared metric-card extraction aligned with dashboard card patterns | Pattern-only | P3 | Good candidate for a shared presentational metric-card |

## C. Keep-As-Is / No-Match Rationale

### Existing Primitive Library

All files under `frontend/src/components/ui/*` are already shadcn/ui-style primitives and should remain the foundation of the frontend. This includes components such as `button`, `card`, `dialog`, `input`, `select`, `table`, `tabs`, `sheet`, `sidebar`, `dropdown-menu`, `command`, `form`, `chart`, `breadcrumb`, `pagination`, and the utility files that support them.

### Domain-Specific Surfaces

- `components/error-boundary.tsx`: standard React boundary, not a replacement target.
- `components/portfolios/confirm-delete-dialog.tsx`: already composes `AlertDialog` well.
- `components/portfolios/portfolio-balances-section.tsx`: card-grid display is a better fit than a data-table pattern.
- `components/stock-analysis/prompt-preview-panel.tsx`: no proven shadcn block maps cleanly to this prompt-rendering surface.
- `components/stock-analysis/run-status-display.tsx`: status/polling UI is domain-specific.
- `components/stock-analysis/run-builder-page.tsx`: orchestration shell; its child controls are the actual migration targets.
- `components/snippet-create-page.tsx` and `components/prompt-template-create-page.tsx`: route wrappers that benefit automatically from form migrations.

### Bootstrap and Logic Layers

- `main.tsx`, `App.tsx`, and `routes.ts` were scanned and explicitly classified as non-replacement bootstrap/routing files.
- `frontend/src/hooks/*`, `frontend/src/lib/*`, and `frontend/src/test/*` were scanned and explicitly classified as logic/infrastructure layers rather than component-replacement targets.

## D. Phased Plan

### Phase 0: Shared Foundations

1. Install `@tanstack/react-table`.
2. Create a shared `DataTable` wrapper based on the shadcn `data-table-demo` pattern.
3. Add shared Zod schemas for the planned RHF migrations.
4. Extract a shared `MetricCard` presentational component.

### Phase 1: Highest-Value Data Surfaces

1. Migrate `portfolio-positions-section.tsx` to a shadcn/TanStack data-table pattern.
2. Migrate `portfolio-trades-section.tsx` to the same shared table system.

### Phase 2: Simple RHF Form Migrations

1. `balance-form-dialog.tsx`
2. `snippet-form.tsx`
3. `prompt-template-form.tsx`
4. `portfolio-form-dialog.tsx`
5. `position-form-dialog.tsx`

### Phase 3: Complex RHF Form Migrations

1. `trading-operation-form.tsx`
2. Extract and migrate the inline config form in `llm-configs.tsx`
3. Migrate `conversation-picker.tsx` create flow
4. Migrate `run-builder-form.tsx`
5. Simplify `run-builder-mode-fields.tsx` around RHF control wiring

### Phase 4: App Shell Migration

1. Replace the custom layout shell with the proven shadcn sidebar composition.
2. Add breadcrumb/header structure where it improves route context.
3. Preserve mobile navigation behavior during the migration.

### Phase 5: Lower-Risk Polish

1. Replace inline card-list actions with `DropdownMenu` in `llm-configs.tsx`, `snippets.tsx`, `prompt-templates.tsx`, and `portfolio-list-page.tsx`.
2. Replace filter selects with combobox patterns where searchability improves usability.
3. Reuse the extracted metric-card pattern in `dashboard.tsx` and `portfolio-detail-page.tsx`.

## Verification Notes

- This plan is planning-only and does not implement code changes.
- The scan now explicitly covers the relevant frontend surface under `frontend/src/` and classifies every area as a replacement target, keep-as-is surface, or scanned out-of-scope layer.
- The plan was Oracle-verified as complete for the original task before being persisted into docs.
