# Text Template Placeholder Metrics Upgrade Plan

> Archive Status: Fully implemented. The metric placeholders described here are live in `backend/app/services/template_compiler_service.py` and exposed in the template editor placeholder browser.

## Overview

This document plans the next upgrade to Ledger's text template system so templates can render quote-backed portfolio and position metrics in addition to the existing metadata, balance, and raw position fields.

The live placeholder compiler remains backend-owned in `backend/app/services/template_compiler_service.py`, so this upgrade moves the existing frontend-only metric math into backend compile-time helpers backed by market quotes.

## Scope

- Add new scalar placeholders for portfolio total value and unrealized P&L.
- Add new scalar placeholders for position market value, unrealized P&L, and unrealized P&L percent.
- Preserve all existing placeholder paths and renderer behavior.
- Keep compile responses as markdown-compatible strings.

## Contract Decisions

### Naming

- Use explicit snake_case names that match the current placeholder contract style.
- Do not add a bare `performance` placeholder because the term is ambiguous.
- Do not add a bare `value` placeholder because it hides whether the number is total portfolio value or position market value.

### Missing Quote Behavior

- Quote-backed placeholders render an empty string when the backend cannot resolve a usable quote.
- This applies to missing quotes, stale-only unavailable paths, and quote currency mismatch paths that are filtered out by market-data logic.

### Metric Semantics

- Portfolio total value includes signed cash balances.
- Position value means market value.
- Performance is represented explicitly as unrealized P&L amount, with an optional percent field at the position level.

## New Placeholder Contract

### Portfolio Placeholders

- `portfolios.<slug>.total_value`
- `portfolios.<slug>.unrealized_pnl`

### Position Placeholders

- `portfolios.<slug>.positions.<SYMBOL>.market_value`
- `portfolios.<slug>.positions.<SYMBOL>.unrealized_pnl`
- `portfolios.<slug>.positions.<SYMBOL>.unrealized_pnl_percent`

## Formulas

### Portfolio Metrics

- `total_value = sum(position.quantity * current_price) + sum(signed_balances)`
- `unrealized_pnl = sum((current_price - average_cost) * quantity)`

### Position Metrics

- `market_value = quantity * current_price`
- `unrealized_pnl = (current_price - average_cost) * quantity`
- `unrealized_pnl_percent = unrealized_pnl / (average_cost * quantity)` when cost basis is non-zero

These formulas intentionally mirror the live frontend analytics in `frontend/src/lib/portfolio-analytics.ts` so the template output matches the portfolio UI.

## Unchanged Behavior

- Existing placeholders such as `name`, `description`, `base_currency`, `balance.*`, and `positions.<SYMBOL>.quantity` remain unchanged.
- `{{portfolios}}`, `{{portfolios.<slug>}}`, and `{{portfolios.<slug>.positions}}` keep their current formatted block and list rendering. Specifically:
  - `_render_portfolio_summary()` does NOT include `total_value` or `unrealized_pnl` in v1.
  - `_render_position_line()` does NOT include `market_value` in v1.
  - Enriching these renderers with metric data is a candidate for a v2 follow-up but is intentionally out of scope here to avoid changing existing compiled template output.
- Unknown roots, slugs, symbols, and unsupported fields continue to use the current sentinel behavior.

## Backend Changes

### Dependency Wiring

- Update `backend/app/api/dependencies.py` so `get_template_compiler_service()` injects `MarketDataService` via `get_market_data_service()`.

### Template Compiler

- Extend `backend/app/services/template_compiler_service.py` to accept `MarketDataService`.
- Fetch quotes once per portfolio during a compile only when a quote-backed placeholder is requested.
- Cache quote results per portfolio for the lifetime of the compile call to avoid repeated fetches. When a template references multiple portfolios, each portfolio's symbols are fetched independently and cached under its `portfolio.id`.

#### Path Dispatch Integration

The compiler's `_resolve()` method dispatches on `parts[2]` (the field name after the slug). The current dispatch order is:
1. `field in _PORTFOLIO_SCALAR_FIELDS` → ORM attribute lookup
2. `field == "balance"` → balance subtree
3. `field == "positions"` → positions subtree
4. else → `[Unknown field: ...]`

New portfolio-level metric fields (`total_value`, `unrealized_pnl`) are NOT ORM attributes, so they cannot be added to `_PORTFOLIO_SCALAR_FIELDS`. Instead:
- Add a new frozenset `_PORTFOLIO_METRIC_FIELDS = frozenset({"total_value", "unrealized_pnl"})`.
- Insert a new dispatch branch after the scalar check and before the unknown-field fallback: `if field in _PORTFOLIO_METRIC_FIELDS: return self._resolve_portfolio_metric(portfolio, field)`.

Similarly, new position-level metric fields (`market_value`, `unrealized_pnl`, `unrealized_pnl_percent`) need a new branch inside `_resolve_positions()` after the `field in _POSITION_SCALAR_FIELDS` check:
- Add a new frozenset `_POSITION_METRIC_FIELDS = frozenset({"market_value", "unrealized_pnl", "unrealized_pnl_percent"})`.
- Insert: `if field in _POSITION_METRIC_FIELDS: return self._resolve_position_metric(position, portfolio, field)`.

#### Private Helpers

- Add private helpers for:
  - `_resolve_portfolio_metric(portfolio, field)` — dispatches to the correct computation
  - `_resolve_position_metric(position, portfolio, field)` — dispatches to the correct computation
  - `_compute_position_market_value(quantity, current_price) -> Decimal | None`
  - `_compute_position_pnl(quantity, average_cost, current_price) -> tuple[Decimal | None, Decimal | None]`
  - `_compute_portfolio_total_value(positions_with_quotes, balances) -> Decimal | None`
  - `_compute_portfolio_unrealized_pnl(positions_with_quotes) -> Decimal | None`
- Resolve the new placeholder paths through the dispatch branches described above.

#### Balance Reuse

The existing `_compute_available_balance()` method already computes the signed balance total needed by the `total_value` formula. Refactor it to expose the raw `Decimal` total (or add a thin wrapper) so `_compute_portfolio_total_value` can reuse it instead of reimplementing balance summation.

#### MarketDataService Integration Note

`MarketDataService.get_quotes()` takes a `portfolio_id: int` and internally re-verifies portfolio existence. Since the compiler already has the `Portfolio` ORM object from `get_by_slug()`, this is a redundant check but harmless. Accept it as-is rather than introducing a new code path that bypasses the existence check.

### Formatting

- Keep money output aligned with the backend's existing `decimal_to_string()` from `app/core/formatting.py`, which uses `format(value, "f")` for full Decimal precision.
- Render the percent placeholder as a decimal fraction string (e.g., `0.1234` for 12.34%). Note that `decimal_to_string()` preserves full Decimal precision, while the frontend's `formatPercent()` rounds to 2 decimal places. This is acceptable because template authors control display formatting, and the backend should provide maximum precision rather than pre-rounding.
- If a position's cost basis is zero, render `unrealized_pnl_percent` as empty string to avoid division by zero.

## Frontend Changes

### Placeholder Browser

- The editor's placeholder reference panel in `frontend/src/pages/templates/editor.tsx` has two layers:
  - Three hardcoded `PlaceholderGroup` components (Portfolio, Balance, Position) at lines 255–292 with literal path arrays.
  - A dynamic section at lines 294–307 that renders per-portfolio concrete slug/symbol shortcuts from the backend tree API.
- New schema-level fields like `total_value` and `market_value` will NOT appear automatically from the backend tree. They must be added manually to the hardcoded `PlaceholderGroup` item arrays:
  - Add `total_value` and `unrealized_pnl` entries to the Portfolio group.
  - Add `market_value`, `unrealized_pnl`, and `unrealized_pnl_percent` entries to the Position group.
- Keep the current click-to-insert workflow unchanged; `insertPlaceholder()` works identically for all entries.

### Types

- `frontend/src/lib/types/text-template.ts` needs no schema shape change. The `PlaceholderTree` type only carries portfolio/position identity data for the dynamic section, not schema-level field definitions.
- The `PlaceholderTreeRead` backend schema in `backend/app/schemas/text_template.py` also stays unchanged for the same reason.

## Test Plan

### Backend API Coverage

- Extend `backend/tests/test_api.py` with template compile assertions for all new placeholders.
- Use the existing `StableQuoteProvider` class (lines 677–720) and the proven `dependency_overrides` pattern (lines 763+) to inject deterministic prices. No new test infrastructure is needed.
- Override `get_quote_provider` on the test app before compile requests so `MarketDataService` receives deterministic prices.
- Assert the new placeholders compile to expected values computed from `StableQuoteProvider` prices and the test's existing portfolio/position/balance data.
- Cover a missing-quote path using the existing `BrokenQuoteProvider` class (lines 669–674) and assert that quote-backed placeholders render empty string.
- Cover the zero-cost-basis edge case and assert that `unrealized_pnl_percent` renders empty string.
- Re-run existing template compile assertions to ensure current placeholders still render exactly as before.

### Regression Focus

- No N+1 quote fetches inside a single portfolio compile.
- No behavior changes for existing object renderers.
- No drift between compiler dispatch branches, hardcoded editor placeholder groups, and test assertions.

## File Touchpoints

- `backend/app/api/dependencies.py` — inject `MarketDataService` into compiler factory
- `backend/app/services/template_compiler_service.py` — new metric frozensets, dispatch branches, helpers, quote caching
- `backend/app/services/quote_provider.py` — imported for `QuoteProviderError` handling (no changes to this file)
- `backend/tests/test_api.py` — new template compile assertions with `StableQuoteProvider` override
- `frontend/src/pages/templates/editor.tsx` — add new entries to hardcoded Portfolio and Position `PlaceholderGroup` arrays

## Risks

- Quote-backed placeholders can slow compile if quote fetching is not batched per portfolio.
- Currency mismatch handling must stay aligned with `MarketDataService` so template math does not silently mix currencies.
- Backend decimal formatting must stay consistent with existing compile output or tests will become brittle.
- The compiler dispatch branches, hardcoded editor placeholder groups, and backend tests must ship together to avoid broken authoring guidance.
- Redundant portfolio existence checks in `MarketDataService.get_quotes()` are harmless but add a minor DB round-trip per portfolio with metric placeholders.

## Execution Order

1. Wire `MarketDataService` into `TemplateCompilerService` via `dependencies.py`.
2. Add `_PORTFOLIO_METRIC_FIELDS` and `_POSITION_METRIC_FIELDS` frozensets and new dispatch branches in the compiler.
3. Implement the private metric computation helpers, reusing `_compute_available_balance()` for the signed balance total.
4. Add per-portfolio quote caching inside the compiler.
5. Add deterministic backend tests using the existing `StableQuoteProvider` and `dependency_overrides` pattern.
6. Add new placeholder entries to the hardcoded `PlaceholderGroup` arrays in `frontend/src/pages/templates/editor.tsx`.

## Notes

- This plan intentionally avoids a plain `performance` placeholder.
- If Ledger later needs richer performance reporting, the safer follow-up contract is to add explicit names such as `realized_pnl`, `total_return_percent`, or methodology-specific return metrics rather than overloading `performance`.
