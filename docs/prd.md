# Product Requirements Document (PRD)

> Status: Current product-scope reference as of 2026-03-21 (`8fd7fee`).

## Product Summary

Ledger is an auth-less portfolio workspace for a single trusted operator. The live product tracks portfolios, deposit and withdrawal balances, aggregate stock positions, delayed market context, simulated trading operations, reusable text templates, persisted markdown reports generated from templates or uploaded directly, and an experimental backtest workspace for historical LLM-guided simulations.

## Problem Statement

Portfolio tracking is easy to fragment across spreadsheets, broker dashboards, notes, and ad hoc prompts. That fragmentation causes four practical issues:

- balances, positions, and simulated trades drift out of sync;
- market context is visible, but not tied cleanly to portfolio state;
- importing or correcting data is tedious when there is no preview step;
- reusable research or reporting templates become stale when they are not connected to live portfolio data.

Ledger solves this by keeping portfolio state, market context, and template rendering in one local system. The product favors explicit user-controlled records over broker sync or automation.

## Target User

- A single operator working in a trusted local or private environment.
- A user who wants manual, editable portfolio records instead of reconciliation-heavy broker integrations.
- A user who wants reusable text templates backed by live portfolio data for summaries, journaling, or downstream LLM prompts.

## Goals

- Keep each portfolio isolated so one workspace cannot leak into another.
- Make balances, positions, CSV imports, and simulated operations easy to understand and correct.
- Show delayed quotes and history as helpful context without making them authoritative.
- Preserve deterministic portfolio math for `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` flows.
- Let the user author templates in the UI and preview compiled output before saving or reusing it.
- Let the user turn template output into point-in-time report snapshots, edit uploaded or generated markdown, and download reports without leaving the app.
- Let the user launch an experimental backtest over a saved portfolio and compare simulated results against benchmarks without leaving the product.
- Keep local persistence authoritative even when provider lookups fail.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, or automatic trade execution.
- Realtime quote streaming, alerts, or background schedulers.
- Tax-lot accounting, FIFO, realized tax reporting, or accounting exports.
- General stock-analysis conversations, response history, snippets, or provider-orchestrated research flows outside the shipped template, report, and backtest surfaces.

## Product Areas

### 1. Portfolio Workspace

- Portfolio list with create, edit, delete, and open flows.
- Portfolio detail workspace with balances, positions, trades, and quote-enriched metrics.
- Clear portfolio isolation in both API scope and UI navigation.

### 2. Cash Accounts

- Balance CRUD inside a portfolio.
- Explicit `DEPOSIT` and `WITHDRAWAL` balance types.
- Portfolio cash math that subtracts withdrawal balances from available cash.

### 3. Positions And Imports

- Manual position CRUD with one aggregate position per symbol.
- Optional symbol-name enrichment via provider lookup and cache.
- CSV preview-before-commit with row-level validation and atomic apply.

### 4. Market Context

- Delayed quote retrieval for portfolio symbols.
- Price-history retrieval for supported ranges.
- Warning and stale-state messaging when quote providers fail or return mismatched currency data.

### 5. Simulated Trading Ledger

- Append-only `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations.
- Deterministic balance and aggregate-position updates.
- Immediate rejection of invalid operations such as oversells, negative cash, or missing positions.

### 6. Template Manager

- Global text-template CRUD.
- Placeholder browser driven by live portfolio slugs and positions.
- Inline compile preview plus stored-template compile-by-id.

### 7. Reports Workspace

- Generate point-in-time report snapshots from saved templates.
- Upload markdown files as reports with optional author, description, and tags metadata.
- Browse, edit, download, and delete reports from dedicated list/detail routes.
- Reuse reports inside templates through `{{reports.<name>...}}` placeholders.

### 8. Backtests Workspace

- Launch historical simulations against an existing or newly created portfolio.
- Configure schedule, benchmarks, LLM endpoint/model settings, price mode, and commission mode per run.
- Monitor in-progress runs, inspect recent activity, and review completed equity, drawdown, and trade-log results.

## Core User Stories

- As a user, I want separate portfolios for different strategies so their balances, positions, and trades stay isolated.
- As a user, I want deposit and withdrawal balances so the portfolio cash picture matches how I actually manage funds.
- As a user, I want to import positions by CSV with a preview step so I can catch bad rows before commit.
- As a user, I want simulated trades and cash events so Ledger can model changes without touching a broker.
- As a user, I want delayed quotes and price history for context while keeping my manually entered records authoritative.
- As a user, I want reusable templates with `{{placeholders}}` so I can render live portfolio summaries without copy-paste work.
- As a user, I want generated or uploaded markdown reports so I can keep point-in-time deliverables alongside my live templates.
- As a user, I want to backtest a saved portfolio over historical market data so I can inspect simulated results, benchmark comparisons, and per-cycle decisions.

## Experience Principles

- Keep local records authoritative.
- Make state corrections cheap and explicit.
- Prefer preview-before-commit for risky actions.
- Preserve degraded-but-usable flows when providers fail.
- Keep templates transparent: the user should see both the source text and compiled result.

## Key Screens

### Dashboard

- Portfolio counts, position counts, balance counts, and latest activity summary.

### Portfolio List

- Portfolio cards with create, edit, delete, and open flows.

### Portfolio Detail Workspace

- Header with portfolio metadata and base currency.
- Tabs for positions, balances, and trades.
- Quote-enriched metrics and warning states.

### CSV Import Flow

- File picker, validation preview, accepted rows, row errors, and commit action.

### Template List

- Template inventory with edit and delete actions.

### Template Editor

- Full-height editor, inline compile preview, and placeholder reference panel.

### Reports List

- Inventory of generated and uploaded reports with generate, upload, download, and delete actions.

### Report Detail

- Markdown read mode, inline text edit mode, and file download from a slug-addressed route.

### Backtests List

- Inventory of launched simulations with progress, terminal-state cleanup, and completed return summaries.

### Backtest Configuration

- Existing/new portfolio flow, template selection or default-template creation, benchmark selection, and per-run LLM and commission settings.

### Backtest Detail

- Running-state progress and recent activity, then completed KPI cards, equity and drawdown charts, trade log, and links to generated reports.

## Success Criteria

- A new portfolio can be created and populated with balances and positions in minutes.
- CSV validation is clear enough that the user can fix bad files without backend intervention.
- Simulated operations update cash and aggregate positions in one step and reject invalid requests deterministically.
- Delayed market data remains visibly non-authoritative and does not block the rest of the workspace.
- A user can create or edit a template, preview compiled output, and reuse it without editing code.
- A user can generate a report from a template or upload a markdown file, then open, edit, download, and delete that report through the UI.
- A user can launch a backtest, watch it progress, and review completed benchmark-relative results plus report-linked trades from the UI.

## Risks And Mitigations

- Public market data can be stale or unavailable; mitigate with warnings, stale flags, and cached-quote fallback.
- Manual records can drift from reality; mitigate with strict validation, duplicate checks, and preview-before-commit imports.
- Template placeholder drift can confuse users; mitigate with a live placeholder browser and compile preview.
- Auth-less deployment is unsafe for public exposure; mitigate by documenting trusted-environment usage clearly.
