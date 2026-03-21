# Test Plan

> Status: Current automated coverage reference as of 2026-03-21 (`8fd7fee`).

This file reflects the existing automated surface only. The documentation refresh did not change application code, add new tests, or promote local-only checks into CI.

## Overview

This document describes the current automated coverage for the live Ledger stack and the most useful next expansion areas. It is intentionally split into current coverage and targeted gaps so the docs do not imply tests exist where they do not.

## Current Tooling

- Backend integration tests: `pytest` against isolated PostgreSQL databases
- Frontend unit/component tests: Vitest + React Testing Library + jsdom
- End-to-end tests: Playwright (Chromium)
- CI runners: GitHub Actions with separate backend-quality, frontend-quality, and Docker smoke-build jobs

## Current Automated Coverage

### Backend: `backend/tests/test_api.py`

The backend suite is the highest-signal regression layer and covers:

- portfolio CRUD and slug validation
- balance CRUD plus `operationType` lock behavior once trading history exists
- position CRUD, symbol lookup, and symbol-name cache reuse
- CSV preview/commit validation and upsert behavior
- trading-operation rules for `BUY`, `SELL`, `DIVIDEND`, and `SPLIT`
- market-data success, warning, cached-quote fallback, and history behavior
- template CRUD, placeholder browsing, inline compile, stored compile-by-id, report placeholder expansion, and cycle detection
- report compile/upload/update/delete/download flows plus placeholder-tree inclusion
- supported legacy schema upgrades, including dropped stock-analysis tables, balance `operation_type` backfill, and report `slug`/`source`/`metadata` backfill

### Backend: `backend/tests/test_backtests_api.py` and `backend/tests/test_backtest_engine.py`

Backtest-specific coverage includes:

- `backtests` table creation and `trading_operations.backtest_id` schema upgrades
- create/list/read/cancel/delete backtest API flows
- largest-deposit-balance selection, default-template creation, and deterministic launch wiring
- startup crash recovery for interrupted `PENDING` or `RUNNING` rows
- NYSE schedule generation for `DAILY`, `WEEKLY`, and `MONTHLY` backtests
- parquet market-data cache write, reuse, and append behavior
- prompt construction, deterministic OpenAI responses, report tagging, trade attribution, and result aggregation

### Frontend Unit And Component Tests

Implemented files:

- `frontend/src/lib/api.test.ts`
- `frontend/src/lib/format.test.ts`
- `frontend/src/lib/markdown-format.test.ts`
- `frontend/src/lib/portfolio-analytics.test.ts`
- `frontend/src/lib/query-keys.test.ts`
- `frontend/src/pages/templates/editor.test.tsx`
- `frontend/src/components/forms/portfolio-form-dialog.test.tsx`
- `frontend/src/components/portfolios/position-form-dialog.test.tsx`
- `frontend/src/components/portfolios/portfolio-positions-section.test.tsx`
- `frontend/src/components/portfolios/trading-operation-form.test.tsx`
- `frontend/src/components/portfolios/record-trading-operation-dialog.test.tsx`
- `frontend/src/components/portfolios/portfolio-trades-section.test.tsx`
- `frontend/src/lib/types/backtest.test.ts`
- `frontend/src/hooks/use-backtests.test.ts`
- `frontend/src/pages/backtests/list.test.tsx`
- `frontend/src/pages/backtests/config.test.tsx`
- `frontend/src/pages/backtests/detail.test.tsx`
- `frontend/src/components/backtests/equity-curve-chart.test.tsx`
- `frontend/src/components/backtests/trade-log-table.test.tsx`

Covered behaviors:

| File / Area | Current Assertions |
|---|---|
| `api.test.ts` | request success/error mapping, base URL selection, query/path encoding, symbol lookup URL generation |
| `format.test.ts` | currency, decimal, percent, date/datetime, compact-number formatting |
| `markdown-format.test.ts` | Prettier-backed markdown normalization while preserving `{{placeholders}}` |
| `portfolio-analytics.test.ts` | quote enrichment, market value, P&L, allocation math, withdrawal sign handling |
| `query-keys.test.ts` | id normalization, market-history symbol normalization, lookup-key normalization |
| backtest hook/type/page/component tests | backtest wire contract guards, 5s polling behavior, config validation, result rendering, chart toggles, and trade-log sorting |
| `templates/editor.test.tsx` | dynamic report selector guidance and click-to-insert placeholder behavior |
| portfolio form/dialog tests | portfolio create/edit validation and UI behavior |
| trading/position component tests | side-specific form behavior, position entry, trade recording, and trades table rendering |

### Frontend E2E

Implemented Playwright specs:

- `frontend/e2e/smoke.spec.ts`
- `frontend/e2e/functional.spec.ts`
- `frontend/e2e/reports.spec.ts`
- `frontend/e2e/backtests.spec.ts`

Covered behaviors:

| File | Current Assertions |
|---|---|
| `smoke.spec.ts` | app boot, dashboard visibility, sidebar links, portfolios route navigation |
| `functional.spec.ts` | portfolio creation flow, portfolio list render, add-position symbol lookup, manual name fallback when lookup fails |
| `reports.spec.ts` | reports sidebar nav, generate from template, upload with metadata, edit/download/delete behavior, template-editor generate shortcut |
| `backtests.spec.ts` | create backtest flow, polling to terminal state, result visibility, terminal delete cleanup |

## Test Environment Matrix

| Test Level | Environment |
|---|---|
| Backend integration | Temporary PostgreSQL databases created and dropped by pytest fixtures |
| Frontend unit/component | jsdom with mocked `ResizeObserver`, `matchMedia`, and `IntersectionObserver` |
| Playwright E2E | Real backend on `8001` with `BACKTEST_TEST_MODE=1`, real frontend on `4173`, PostgreSQL-backed flows |
| Manual local full stack | `start.sh` on backend `28000`, frontend `25173`, PostgreSQL `25432` |

## CI Coverage

### `backend-quality`

- `ruff check app tests`
- `black --check app tests`
- `isort --check-only app tests`
- `mypy app`
- `pytest`

### `frontend-quality`

- `pnpm lint`
- `pnpm build`
- `pnpm test:e2e`

### `docker-build-smoke`

- builds both backend and frontend Dockerfiles for `linux/amd64`
- runs only after both quality jobs pass

Local-only but recommended checks:

- `cd frontend && pnpm typecheck`
- `cd frontend && pnpm test:run`

## Execution Commands

```bash
# Backend
cd backend && uv run pytest tests/test_api.py tests/test_backtests_api.py tests/test_backtest_engine.py

# Frontend unit/component tests
cd frontend && pnpm test:run

# Frontend E2E
cd frontend && pnpm test:e2e

# Full local validation
cd backend && uv run ruff check app tests && uv run black --check app tests && uv run isort --check-only app tests && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run && pnpm test:e2e
```

## Highest-Value Next Coverage

- Add Playwright coverage for balance CRUD and trading-operation flows end to end.
- Add Playwright coverage for template create/edit/delete and inline compile preview beyond the report-generation shortcut.
- Add route-level frontend tests for `PortfolioDetailPage` degraded quote-warning states.
- Add direct tests for quote warning rendering and cached-quote fallback in portfolio UI.
- Add route-level frontend tests for report upload validation edge cases and report detail error states.
- Add more browser-level coverage for backtest failure, cancellation, and `LLM_DECIDED` pricing branches.
- Add a root-level smoke check around `start.sh` once CI support for Docker-in-Docker orchestration is acceptable.
