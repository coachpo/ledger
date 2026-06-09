# FRONTEND PORTFOLIOS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/portfolios/` owns the live portfolio inventory and workspace detail routes. The list page handles create/edit/delete entry points, table inventory search, table selection, and bulk delete, while the detail page composes balances, positions, trades, quotes, and derived portfolio metrics inside one routed workspace.

Extension model: statically resident Finance Workspace extension.

## WHERE TO LOOK

| Task                    | Location                                                                                                                                | Notes                                                                                                                           |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Portfolio inventory     | `list.tsx`                                                                                                                              | newest-updated ordering, modal create/edit, ResourceToolbar search, table selection/bulk delete, and delete confirmation |
| Portfolio workspace     | `detail.tsx`                                                                                                                            | quote-enriched metrics, tab shell, edit/delete, and section orchestration                                                       |
| Feature UI              | `../../components/portfolios/AGENTS.md`                                                                                                 | balances, positions, trades, dialogs, and shared delete affordances                                                             |
| Query + mutation policy | `../../hooks/use-portfolios.ts`, `../../hooks/use-balances.ts`, `../../hooks/use-positions.ts`, `../../hooks/use-trading-operations.ts` | route reads, invalidation, and CRUD flows                                                                                       |
| Derived portfolio math  | `../../lib/portfolio-analytics.ts`                                                                                                      | enrichment, total value, signed balances, and P&L helpers                                                                       |
| Focused test entry      | `list.test.tsx`                                                                                                                         | empty-state typography and preserved page actions                                                                               |

## CONVENTIONS

- `list.tsx` owns route-level modal state, navigation, ResourceToolbar search, table selection state, and bulk delete; request/dialog policy stays in hooks and shared dialogs.
- New portfolio creation should navigate into the created detail route after success; edit/delete stay list-local until the mutation settles.
- `detail.tsx` is the orchestration hub for the workspace. Keep quote enrichment, allocation math, and signed balance helpers in shared analytics utilities instead of reimplementing them inline.
- Quote failures are degradations, not hard blockers. Keep balances, positions, and trade history usable even when quote warnings are present.
- The detail route stays tabbed across Positions, Balances, and Trades; section-specific write logic belongs in the portfolio components and hooks, not in ad-hoc page helpers.
- Portfolio detail pages are routable but not sidebar destinations; keep back-navigation explicit and route-safe.
- Route metadata marks portfolio list as an extension-owned inventory route and portfolio detail as an extension-owned detail route. Disabled Finance Workspace state comes from the runtime gate, not from list or detail special cases.
- Portfolio table navigation must remain explicit links. The table owns row checkboxes, select-all for shown rows, the bottom bulk-action bar, and clear selection. Create, edit, delete, trade, and dialog controls remain buttons or form controls.

## ANTI-PATTERNS

- Do not spread decimal parsing or quote math across the route body when shared analytics helpers already own it.
- Do not treat quote warnings as fatal errors that block the rest of the workspace.
- Do not push section-specific mutation logic down into generic table helpers.
- Do not add dedicated “proves not” tests for routine removal-only checks in this route family; manual confirmation is enough unless the absence itself is a shipped contract.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/portfolios/list.test.tsx
pnpm lint
pnpm typecheck
pnpm build
```
