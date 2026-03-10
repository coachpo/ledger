# Product Requirements Document (PRD)

## Product Summary

The product is a simple portfolio workspace for manually tracking stock positions and cash balances across multiple isolated portfolios. It also supports delayed public market prices and basic simulated buy or sell operations so the user can test portfolio changes without broker integration.

## Problem Statement

Users often manage portfolio snapshots in spreadsheets and perform paper trading in disconnected tools. That creates duplicate entry, weak isolation between portfolios, and no reliable way to apply balance changes and position updates consistently after each simulated trade.

## Target User

- A single operator or trusted internal user managing one or more investment portfolios.
- A user who values simple record-keeping over advanced analytics or brokerage automation.
- A user who is comfortable entering positions manually or by CSV import.

## Goals

- Make portfolio setup fast and explicit.
- Keep each portfolio isolated so experimentation in one portfolio does not affect another.
- Support both manual and CSV-based position maintenance.
- Keep cash balance updates and trading-operation effects easy to understand.
- Show delayed market prices as guidance without pretending to be realtime.

## Non-Goals

- Realtime trading or order routing.
- Authentication or account management.
- FIFO, tax lots, dividend processing, or performance analytics.
- Complex reconciliation, audit workflows, or accounting exports.

## Core User Stories

- As a user, I want to create separate portfolios for different strategies so they remain isolated.
- As a user, I want to maintain my current positions manually so I can correct data quickly.
- As a user, I want to upload a CSV list of positions so I can avoid repetitive data entry.
- As a user, I want to track portfolio balances so I can see how much cash is available before a simulated trade.
- As a user, I want to submit a simulated buy or sell operation with commission so positions and balances update consistently.
- As a user, I want to see delayed public prices for my symbols so I have an indicative reference point.

## MVP Features

### 1. Portfolio Workspace

- Portfolio list view.
- Portfolio create, edit, and delete actions.
- Portfolio detail workspace with sections for balances, positions, trading operations, and market data.

### 2. Balance Management

- List balances for the active portfolio.
- Create a balance record with label and amount.
- Edit or delete a balance record.

### 3. Position Management

- Create, edit, and delete a position manually.
- View positions as an aggregate table keyed by symbol.
- Show average cost and quantity per position.

### 4. CSV Import

- Upload a CSV file for the active portfolio.
- Validate headers and row values before commit.
- Preview accepted rows and row-level errors.
- Apply validated rows as `upsert by symbol`.

### 5. Indicative Market Data

- Fetch delayed public quotes for symbols in the active portfolio.
- Show last price, provider, and as-of timestamp.
- Mark quotes as delayed or indicative.

### 6. Simulated Trading Operations

- Submit `BUY` or `SELL` operation forms.
- Enter quantity, price, commission, trade date/time, and settlement balance.
- Apply the operation to the aggregate position and balance immediately.
- Reject trades that would leave the selected balance negative or attempt to sell more than the held quantity.
- List recent simulated trading operations in the portfolio workspace.

Manual balance edits, manual position edits, and CSV imports remain the source of truth for current state in MVP. Trading operations are kept as a historical simulation log and are not replayed to rebuild portfolio state.

## User Experience Principles

- Keep each workflow obvious and form-driven.
- Make portfolio isolation visible in the UI at all times.
- Prefer explicit validation messages over silent corrections.
- Keep market data visually secondary to user-entered records because the prices are only indicative.
- Make simulated-trade effects immediate and understandable.

## Key Screens

### Portfolio List

- Shows all portfolios.
- Supports create, edit, delete, and open actions.

### Portfolio Detail

- Header with portfolio name, description, and base currency.
- Balance section with CRUD actions.
- Position section with CRUD and CSV import actions.
- Trading operation section with submit form and recent history.
- Market data panel with delayed quotes and freshness metadata.

### CSV Import Dialog

- File picker.
- Template reminder.
- Validation preview with accepted rows and errors.
- Commit action.

## Success Criteria

- A new portfolio can be created and populated with balances and positions in under five minutes.
- CSV import errors are understandable enough for the user to fix the file without backend support.
- A simulated trade updates both the chosen balance and the aggregate position in one step.
- Invalid trades are rejected when cash would go negative or sell quantity exceeds the held amount.
- The product communicates delayed data clearly enough that users do not confuse it with realtime execution data.

## Risks and Mitigations

- Public market data can be stale or unavailable; mitigate by surfacing freshness metadata and never blocking manual records.
- No authentication means the product is unsuitable for untrusted public exposure; mitigate by documenting trusted-environment usage.
- CSV files can be inconsistent; mitigate with strict validation and preview-before-commit behavior.
- Lack of FIFO may not match accounting expectations; mitigate by stating average-cost behavior clearly.

## Release-Ready Definition

- Portfolio, balance, and position CRUD work for isolated portfolios.
- CSV import validates and commits positions correctly.
- Delayed quotes can be retrieved and displayed with as-of metadata.
- Simulated buy and sell operations update balances and positions correctly.
- All out-of-scope items remain excluded from the MVP.
