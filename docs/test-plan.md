# Test Plan — Ledger Frontend

## 1. Overview

This document describes the current automated test coverage for the rewritten frontend and the next logical areas to expand. It is intentionally split into **current coverage** and **planned coverage** so the repo docs do not imply tests exist when they do not.

### Tools
- **Unit tests**: Vitest + React Testing Library + jsdom
- **E2E tests**: Playwright (Chromium)
- **Mocking**: `vi.fn()` and fetch stubs in unit tests

### Coverage Targets
- API client (`src/lib/api.ts`): 90%+
- Formatting utilities (`src/lib/format.ts`): 100%
- Portfolio analytics (`src/lib/portfolio-analytics.ts`): 90%+
- E2E: Route smoke coverage plus critical CRUD and response-viewer journeys

---

## 2. Current Automated Coverage

### 2.1 Unit Tests

Implemented test files:

- `src/lib/api.test.ts`
- `src/lib/format.test.ts`
- `src/lib/portfolio-analytics.test.ts`

Covered behaviors:

| File | Current Assertions |
|------|--------------------|
| `src/lib/api.test.ts` | request success/error handling, base URL selection, query encoding |
| `src/lib/format.test.ts` | currency, decimal, percent, and date formatting helpers |
| `src/lib/portfolio-analytics.test.ts` | quote enrichment, total value, P&L, and allocation helpers |

### 2.2 E2E Tests

Implemented Playwright specs:

- `e2e/smoke.spec.ts`
- `e2e/functional.spec.ts`

Covered behaviors:

| File | Current Assertions |
|------|--------------------|
| `e2e/smoke.spec.ts` | app boot, sidebar presence, all six route URLs |
| `e2e/functional.spec.ts` | portfolio creation flow, portfolio list render, prompt templates/snippets pages render, responses page render |

---

## 3. Planned Coverage Expansion

These areas are not fully implemented yet, but they are the next useful additions.

### 3.1 Query / Hook Tests

| Area | Planned Assertions |
|------|--------------------|
| `use-portfolios.ts` | list fetch, create/update/delete invalidation, error states |
| `use-market-data.ts` | disabled queries without symbols, stale quote handling |
| `use-stock-analysis.ts` | conversation listing, version queries, response filtering |
| `query-keys.ts` | tuple stability and portfolio-scope invalidation |

### 3.2 Component Tests

| Area | Planned Assertions |
|------|--------------------|
| `PortfolioListPage` | create/edit/delete flows and empty states |
| `PortfolioDetailPage` | positions/balances/trades tabs and degraded data states |
| `TradingOperationForm` | side-specific fields for BUY/SELL/DIVIDEND/SPLIT |

### 3.3 E2E Growth Areas

| Area | Planned Assertions |
|------|--------------------|
| Portfolio detail | add balances, positions, and trades end-to-end |
| Global stock-analysis resources | create/edit/delete templates and snippets |
| Responses page | portfolio and conversation filtering against seeded data |

---

## 4. Test Data Strategy

| Test Level | Data Source |
|------------|------------|
| Unit tests | Hardcoded fixtures matching frontend API types |
| Future component tests | Mocked fetch responses with React Query providers |
| E2E tests | Real backend on port `8001`; test data created during the scenario |

---

## 5. CI Integration

```yaml
# Frontend quality job
- pnpm typecheck
- pnpm lint
- pnpm test:run
- pnpm build
- pnpm test:e2e
```

---

## 6. Test Execution Commands

```bash
# Run unit tests once
cd frontend && pnpm test:run

# Run Vitest in watch mode
cd frontend && pnpm test

# Run a specific unit test file
cd frontend && pnpm test:run src/lib/format.test.ts

# Run E2E tests
cd frontend && pnpm test:e2e

# Run E2E with Playwright UI
cd frontend && pnpm exec playwright test --ui
```

---

## 7. Gaps And Future Work

- Add React Query hook tests around invalidation and response filtering behavior.
- Add component tests for the portfolio detail workspace and response browser.
- Add stronger Playwright assertions for resource CRUD and response filtering.
- Add accessibility and visual-regression coverage once the UI stabilizes.
