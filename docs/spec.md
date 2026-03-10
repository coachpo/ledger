# Technical Specification

## Overview

This specification defines the MVP behavior for an auth-less portfolio application built with a React/Vite/shadcn frontend, a FastAPI backend, and PostgreSQL persistence. The system manages isolated portfolios, balances, positions, delayed public market data, and simulated buy or sell operations with simple average-cost updates.

## Architecture

### Frontend

- Vite + React application.
- shadcn components for forms, dialogs, tables, tabs, alerts, and buttons.
- Feature areas: portfolio list, portfolio detail workspace, balances, positions, CSV import, trading operations, market data.
- State strategy: route-driven pages plus API-backed client state for active portfolio resources.

### Backend

- FastAPI REST API.
- Service layers for portfolios, balances, positions, CSV import, trading operations, and market data.
- PostgreSQL as the system of record.
- Quote adapter layer for public delayed market data providers.

### Database

- Relational schema with portfolio-scoped resources.
- Decimal-safe numeric columns for quantities, prices, amounts, and commission.
- Referential integrity for portfolio-owned resources.

## Domain Model Rules

### Portfolio Isolation

- All portfolio-owned records carry `portfolio_id`.
- Reads and writes always scope through the active portfolio.
- No position, balance, or trading operation can belong to more than one portfolio.

### Balances

- A balance record represents available cash within a portfolio.
- Required fields: label and amount.
- Currency is derived from the portfolio base currency.
- Currency must match the portfolio base currency.
- Amount must be greater than or equal to zero.

### Positions

- A position is an aggregate current holding for one symbol in one portfolio.
- Required fields: symbol, quantity, average_cost.
- Currency is derived from the portfolio base currency.
- `symbol` is stored uppercase after normalization.
- `quantity` must be greater than zero.
- `average_cost` must be greater than or equal to zero.
- Only one active position per `(portfolio_id, symbol)` is allowed.

### Trading Operations

- A trading operation is a persisted simulated `BUY` or `SELL` event.
- Trading operations are append-only records.
- Each trading operation updates one portfolio, one symbol, and one selected balance.
- Trading operations persist both the current `balance_id` reference and a `balance_label` snapshot for history readability.
- Commission is an absolute amount in the portfolio base currency.
- Current `balances` and `positions` remain the source of truth for portfolio state; trading operations are a historical simulation log only.

### Market Data

- Market data is external and non-authoritative.
- The backend requests delayed public quotes on demand and may cache them locally.
- Quotes must include provider name and as-of timestamp when available.

## Frontend Specification

### Routes

- `/portfolios` - portfolio list.
- `/portfolios/:portfolioId` - portfolio detail workspace.

### Portfolio Detail Layout

- Header: portfolio metadata and top-level actions.
- Balances section: table plus create/edit/delete dialog.
- Positions section: table plus manual CRUD and CSV import dialog.
- Trading operations section: form plus recent history table.
- Market data section: latest indicative quotes for symbols in the portfolio.

### Key UI Components

- `PortfolioTable`
- `BalanceTable`
- `PositionTable`
- `CsvImportDialog`
- `TradingOperationForm`
- `TradingOperationTable`
- `MarketQuotePanel`

### UX Behavior

- All destructive actions require confirmation.
- CSV validation errors are shown per row before commit.
- Market data displays a delayed or indicative label.
- Trading operation submission returns updated balance and position data so the UI can refresh immediately.

## Backend Specification

### Modules

- `portfolios` router/service/repository
- `balances` router/service/repository
- `positions` router/service/repository
- `csv_import` service and validators
- `trading_operations` router/service/repository
- `market_data` router/service/provider adapter

### Validation Rules

- All IDs are UUIDs.
- Monetary and quantity fields use decimal parsing, never floating-point parsing.
- Unknown portfolio or resource IDs return `404`.
- Invalid request payloads return `422` with structured details.
- Business-rule violations return `400` with explicit error codes.

## CSV Import Specification

### Supported File Format

- MIME type: `text/csv` or file extension `.csv`.
- Required headers: `symbol`, `quantity`, `average_cost`.
- Optional header: `name`.

### Row Validation

- `symbol` must be present and non-empty.
- `quantity` must parse as decimal and be greater than zero.
- `average_cost` must parse as decimal and be greater than or equal to zero.
- Duplicate symbols inside the uploaded file are rejected.

### Import Behavior

- Import runs against one selected portfolio.
- Preview validates the file and returns accepted rows plus row-level errors.
- Commit applies `upsert by symbol`.
- Existing symbols in the portfolio are updated.
- New symbols in the portfolio are inserted.
- Positions not present in the file remain unchanged.

### Failure Handling

- Invalid file type returns `400`.
- Missing required headers returns `400` with header details.
- Row validation failures return `422` with row numbers and messages.
- Commit is atomic: either all validated rows apply or none do.

## Trading Operation Calculation Rules

### Shared Inputs

- `quantity > 0`
- `price >= 0`
- `commission >= 0`

### Buy Operation

- `gross_cost = quantity * price`
- `cash_impact = gross_cost + commission`
- The selected balance must have `amount >= cash_impact`.
- New position quantity = `current_quantity + quantity`.
- New aggregate book cost = `(current_quantity * current_average_cost) + gross_cost + commission`.
- New average cost = `new_book_cost / new_quantity`.
- Selected balance amount decreases by `cash_impact`.

### Sell Operation

- Sell quantity must not exceed current position quantity.
- `gross_proceeds = quantity * price`
- `cash_impact = gross_proceeds - commission`
- Current average cost remains the basis for the remaining position.
- Remaining quantity = `current_quantity - quantity`.
- The resulting selected balance must remain greater than or equal to zero after applying `cash_impact`.
- If remaining quantity is zero, the position is deleted.
- If remaining quantity is greater than zero, the average cost remains unchanged.
- Selected balance amount increases by `cash_impact`.

### Explicit Exclusions

- No FIFO.
- No short selling.
- No realized PnL ledger.
- No tax reporting logic.

## Market Data Behavior

- Quote lookup is best-effort.
- The market-data adapter can use a public provider such as Yahoo Finance wrappers, Alpha Vantage, or another delayed public source.
- Quote responses should include `symbol`, `price`, `currency`, `provider`, `as_of`, and `is_stale`.
- If the provider quote currency does not match the portfolio base currency, the quote is treated as unavailable in MVP.
- If the provider fails, the backend should return the last cached quote if available, otherwise return no quote and a warning.

## Transaction Boundaries

- A trading operation and its related balance/position updates must commit in one database transaction.
- CSV import commit must commit in one database transaction.
- Portfolio delete cascades to balances, positions, and trading operations.

## Error Format

```json
{
  "code": "validation_error",
  "message": "CSV validation failed",
  "details": [
    {
      "row": 4,
      "field": "quantity",
      "issue": "Must be greater than zero"
    }
  ]
}
```

## Implementation Notes

- FastAPI CSV upload endpoints should use `UploadFile` with `multipart/form-data`.
- API contracts should use strings for decimal values to avoid precision loss across the frontend/backend boundary.
- The backend should expose quote freshness so the frontend can label delayed data correctly.

## References

- FastAPI request file handling: `UploadFile` and `multipart/form-data` guidance.
- Public delayed quote patterns from widely used portfolio-tracking tooling.
- Existing repo workflow expectations: Python 3.13 backend and Node 22 frontend in CI.
