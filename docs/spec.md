# Technical Specification

> Status: Current live-code reference as of 2026-03-21 (`8fd7fee`).

## Overview

Ledger is an auth-less portfolio application with four live capabilities:

- portfolio tracking and simulation for balances, positions, market context, CSV imports, and manual operations;
- text-template management with server-side placeholder resolution against live portfolio data and persisted reports;
- markdown report generation, direct JSON creation, upload, download, and edit flows built on top of the template system;
- backtests that run historical LLM-guided simulations over a saved portfolio and persist progress plus result curves.

Legacy stock-analysis tables and provider helper code still exist as upgrade-cleanup or dormant reference material, but they are not part of the live API or frontend router.

## Scope Boundaries

- The live API surface includes portfolios, balances, positions, market data, trading operations, templates, reports, and backtests.
- There is no general-purpose stock-analysis route tree, snippet manager, or response viewer outside the dedicated backtest workflow.
- Templates are simple text documents with one `content` field, not multi-step workflows.
- Quote and history providers are best-effort enrichment, not sources of truth.

## Runtime Topology

### Root Workspace

- `backend/` and `frontend/` are git submodules.
- `start.sh` is the canonical local orchestrator.
- Local full-stack ports are PostgreSQL `25432`, backend `28000`, and frontend `25173`.

### Playwright Environment

- Playwright starts its own backend on `8001` and frontend on `4173`.
- This environment is intentionally separate from `start.sh` so E2E runs stay predictable.
- The Playwright backend startup script sets `BACKTEST_TEST_MODE=1` so backtest flows stay deterministic under E2E.

## Backend Architecture

### App Structure

- FastAPI follows the modular `APIRouter` pattern under `backend/app/api/`.
- `backend/app/main.py` owns app creation, CORS, healthcheck, and global error translation.
- `backend/app/api/dependencies.py` is the composition root for request-scoped SQLAlchemy sessions and services.

### Layer Responsibilities

- `app/api/` handles request routing and typed request/response boundaries.
- `app/services/` owns business rules, transaction boundaries, and provider integration.
- `app/repositories/` owns SQLAlchemy query patterns.
- `app/models/` owns table names, constraints, indexes, and relationships.
- `app/schemas/` owns camelCase contracts, validation, and serialization.

### Key Services

- `PortfolioService`: portfolio CRUD plus portfolio existence checks.
- `BalanceService`: balance CRUD, duplicate-label checks, and `operationType` lock enforcement after trading history exists.
- `PositionService`: position CRUD plus symbol-name lookup and cache writes.
- `CsvImportService`: UTF-8 CSV validation, preview, and atomic upsert-by-symbol commit.
- `TradingOperationService`: deterministic `BUY`/`SELL`/`DIVIDEND`/`SPLIT` math and append-only operation logging.
- `MarketDataService`: delayed quote retrieval, cached fallback, staleness calculation, and history fetches.
- `TextTemplateService`: global template CRUD.
- `TemplateCompilerService`: `{{portfolios.<slug>...}}` and `{{reports.<name>...}}` placeholder resolution, compile preview, and report-content re-compilation.
- `ReportService`: compiled-report creation, direct JSON report creation, markdown uploads, slug/name generation, content updates, and download lookups.
- `BacktestService`: backtest CRUD, default-template creation, deposit-balance selection, cancellation, delete cleanup, and background launch.
- `BacktestEngine`: NYSE schedule generation, parquet-backed history loading, OpenAI Responses calls, report persistence, simulated trade execution, and result aggregation.

## Frontend Architecture

### App Shell

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- Routing is flat under `frontend/src/routes.ts` and mounted through `Layout`.
- The live route set is `/`, `/portfolios`, `/portfolios/:portfolioId`, `/templates`, `/templates/new`, `/templates/:templateId/edit`, `/reports`, `/reports/:slug`, `/backtests`, `/backtests/new`, and `/backtests/:backtestId`.

### State Management

- TanStack Query owns all server state.
- Shared endpoint wrappers live in `frontend/src/lib/api/*.ts`.
- Query keys are centralized in `frontend/src/lib/query-keys.ts`.
- Portfolio-scoped mutations invalidate through `invalidatePortfolioScope()`.
- Template and report flows use their own query-key namespaces.

### Page Responsibilities

- `Dashboard` renders cross-portfolio summary metrics and retry states.
- `PortfolioListPage` handles portfolio create/edit/delete flows.
- `PortfolioDetailPage` orchestrates balances, positions, trades, and quote-enriched metrics.
- `TemplateListPage` manages template inventory.
- `TemplateEditorPage` handles inline compile preview, placeholder insertion, markdown formatting, save flows, and direct report generation for saved templates.
- `ReportListPage` manages report inventory, template-driven generation, markdown uploads, and delete/download actions.
- `ReportDetailPage` handles markdown rendering, textarea edits, and markdown downloads.
- `BacktestListPage` shows run inventory, progress, terminal delete actions, and completed-return summaries.
- `BacktestConfigPage` handles existing or new portfolio launch flows, template selection or default-template creation, benchmark selection, and per-run LLM plus commission settings.
- `BacktestDetailPage` polls active runs, renders recent activity while running, and shows KPI cards, result curves, trade logs, and report links after completion.

## Domain Rules

### Portfolio Isolation

- All portfolio-owned records scope through `portfolio_id`.
- Reads and writes never cross portfolio boundaries.
- Templates are global; portfolio data only enters templates at compile time.

### Balance Model

- Balances store `label`, `amount`, `operation_type`, and `currency`.
- `operation_type` is either `DEPOSIT` or `WITHDRAWAL`.
- `BUY`, `SELL`, and `DIVIDEND` target deposit balances; `SPLIT` does not use a balance.
- Portfolio cash calculations subtract withdrawal balances.

### Position Model

- Positions are aggregate holdings keyed by `(portfolio_id, symbol)`.
- Symbols are normalized to uppercase.
- `last_source` records whether a position came from manual entry, CSV import, or simulation.

### Trading Operations

- Operations are append-only simulated events.
- `BUY` creates or updates a position and decreases deposit cash.
- `SELL` rejects oversell, increases deposit cash, and deletes the position on full sell-down.
- `DIVIDEND` requires an existing position and changes only cash.
- `SPLIT` requires an existing position and changes only quantity plus average cost.
- Each operation snapshots `balance_label` so history remains readable if the original balance is deleted.

### Market Data

- Quotes are cached by provider, symbol, and `as_of` timestamp.
- Cached quote fallback is allowed when live provider fetch fails.
- Currency mismatch suppresses the quote and returns a warning.
- History supports `1mo`, `3mo`, `ytd`, `1y`, and `max` ranges.

### Reports

- Reports are stored markdown snapshots with unique `name` and `slug`.
- Compiled reports derive timestamped snake_case names from template names and store `source="compiled"`.
- Uploaded reports store `source="uploaded"`; direct JSON-created reports store `source="external"`.
- Report metadata is an extensible JSON object with known fields such as `author`, `description`, `tags`, and optional `analysis` metadata.
- Report listing supports optional filters on the canonical metadata subset: `analysis.ticker`, `analysis.reviewType`, `analysis.portfolioSlug`, top-level `tags`, and `source`.
- Report list ordering is stable newest first: `created_at DESC, id DESC`.
- Reports are addressed by `slug` in the API and frontend routes, but by `name` inside template placeholders.
- Updating a report only changes `content`; report metadata is immutable after creation.

### Backtests

- Backtests are addressed by numeric id and move through `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED` states.
- Launch requires an existing portfolio, a deposit balance, one or more benchmark symbols, and per-run LLM connection settings.
- `BacktestService` persists the selected deposit balance id so trade execution stays anchored to one cash source.
- `BacktestEngine` writes `recent_activity` during active runs and stores completed `results` as JSON when the run finishes.
- Generated analysis reports are tagged with `backtest_<id>` and simulated trades are written with `trading_operations.backtest_id` for cleanup and attribution.
- Startup repair marks interrupted `PENDING` or `RUNNING` rows failed so the UI never polls a dead job forever.

## Template System

### Placeholder Grammar

```text
{{portfolios}}
{{portfolios.<slug>}}
{{portfolios.<slug>.name}}
{{portfolios.<slug>.balance.amount}}
{{portfolios.<slug>.positions.AAPL.quantity}}
{{reports}}
{{reports.monthly_report_20260317_143052.content}}
{{reports.latest}}
{{reports.latest("AAPL").content}}
{{reports[0].name}}
{{reports.by_tag("weekly_review").latest.name}}
{{inputs.ticker}}
{{reports.latest(inputs.ticker).content}}
{{portfolios.by_slug(inputs.portfolio_slug).positions.by_symbol(inputs.ticker).quantity}}
```

### Resolution Rules

- Resolution is single-pass regex substitution.
- The root namespaces are `inputs`, `portfolios`, and `reports`.
- `balance` resolves to the computed available balance for the portfolio, not an individual balance row.
- `positions` resolves either to a rendered list or to a symbol-specific object path.
- `reports.<name>.content` re-compiles the stored markdown body so embedded portfolio/report placeholders resolve against current live data.
- Runtime inputs are available during compile as `inputs.<name>`.
- Dynamic portfolio selectors support `by_slug(...)` and `positions.by_symbol(...)` so one stored template can target different portfolios and symbols at compile time.
- Dynamic report selectors support the first selector set: `latest`, `latest("TICKER")`, zero-based `[index]`, and `by_tag("tag").latest`.
- Dynamic report selectors can consume runtime inputs inside selector arguments, such as `reports.latest(inputs.ticker)` and `reports.by_tag(inputs.analysis_tag).latest`.
- Dynamic report selectors can be followed by `.name`, `.created_at`, or `.content` after they resolve to a single report.
- Missing runtime inputs resolve to explicit sentinel text such as `[Missing input: ticker]`.
- Valid dynamic report selectors that match no reports resolve to an empty string.
- Malformed dynamic report selectors resolve to an explicit sentinel string.
- Report-content recursion uses cycle detection and renders `[Circular report reference: ...]` when a loop is found.
- Unknown roots and malformed field paths render explicit sentinel text such as `[Unknown field: ...]`, while valid dynamic selectors that match no portfolio or report resolve to an empty string.

### Placeholder Tree Endpoint

- The placeholder tree exposes live portfolio slugs, names, base currency, known positions, and live report names plus creation timestamps.
- The frontend uses that tree to build the editor reference panel and click-to-insert helper.

## Data Flow Highlights

### Portfolio Detail Flow

1. Frontend loads portfolio, balances, positions, and trading operations in parallel.
2. Frontend derives the symbol list from positions.
3. Frontend requests delayed quotes for those symbols.
4. Shared analytics helpers compute total value, cash, unrealized P&L, and allocation data.

### CSV Import Flow

1. User uploads a CSV file.
2. Backend validates headers, UTF-8 encoding, numeric fields, and duplicate symbols.
3. Preview returns accepted rows and row errors without writing data.
4. Commit revalidates, applies atomic upserts, and returns inserted/updated/unchanged counts.

### Template Compile Flow

1. User types template content in the editor.
2. Frontend debounces content changes and optional runtime inputs.
3. Backend compiles placeholders against live portfolio/report data plus any runtime inputs.
4. Frontend renders compiled output side-by-side with the source template.

### Report Generation Flow

1. User selects a saved template from the reports page or clicks Generate Report from the template editor.
2. Optional runtime inputs are supplied when the template is parameterized.
3. Backend compiles the template through `TemplateCompilerService`.
4. `ReportService` persists the compiled markdown as a new `reports` row with generated `name`/`slug` and `source="compiled"`.
5. The reports page flow navigates directly to `/reports/:slug`; the template-editor flow shows a success toast with a `View` action that can open the new report.

### Direct Report Create Flow

1. External automation or a manual client posts JSON to `/api/v1/reports`.
2. Backend validates `content`, optional `name`, optional `slug`, and extensible `metadata`.
3. `ReportService` persists the markdown as a new `reports` row with `source="external"`.
4. The report becomes available through the existing slug-based read, list, update, delete, and download routes.

### Backtest Launch Flow

1. User opens `/backtests/new` and either selects an existing portfolio or creates a new one plus an initial cash balance.
2. Frontend posts the validated payload to `POST /api/v1/backtests` with either an existing template id or `createTemplate=true`.
3. `BacktestService` persists the `backtests` row, selects a deposit balance, optionally creates the default template, and submits `BacktestEngine` to the executor.
4. `BacktestDetailPage` polls `GET /api/v1/backtests/{id}` every 5 seconds while the run is active.
5. `BacktestEngine` writes reports, trades, recent activity, and final result curves back into the shared database.

## CI And Verification

- Backend CI runs `ruff`, `black --check`, `isort --check-only`, `mypy`, and `pytest`.
- Frontend CI runs `pnpm lint`, `pnpm build`, and `pnpm test:e2e`.
- Local validation additionally includes `pnpm typecheck` and `pnpm test:run`.
- Docker smoke builds run after both quality jobs and build `backend` and `frontend` images for `linux/amd64`.
- High-signal backtest regression coverage lives in `backend/tests/test_backtests_api.py`, `backend/tests/test_backtest_engine.py`, and `frontend/e2e/backtests.spec.ts`.
