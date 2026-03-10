# Requirements Document

## Purpose

Design a simple investment portfolio application for trusted use without user authentication. The application manages isolated portfolios, stock positions, cash balances, delayed public market data, and simulated buy or sell operations with commission.

## Product Scope

### In Scope

- Portfolio CRUD with strict isolation between portfolios.
- Manual position CRUD inside a portfolio.
- Position import by CSV upload.
- Manual balance CRUD inside a portfolio.
- Delayed public market data for indication only.
- Simulated buy and sell operations with commission applied.

### Out of Scope

- User authentication, authorization, or multi-tenant access control.
- Realtime quotes, websocket streaming, or broker connectivity.
- FIFO, tax lots, realized tax reporting, or advanced accounting.
- Short selling, options, margin, dividends, and corporate actions.
- Performance analytics, alerts, news, and social features.

## Operating Assumptions

- The application is used in a trusted environment because there is no login layer.
- Each portfolio is an isolated workspace with its own positions, balances, and trading operations.
- A portfolio has a base currency. Balances, positions, prices, and trading operations inside that portfolio use the same currency for MVP simplicity.
- Commission is provided as an absolute amount on each simulated trading operation and applied directly to the cash impact.
- Market data is delayed and indicative; it supports display and simulation assistance only.

## Functional Requirements

### FR-1 Portfolio Management

- The system must let the user create a portfolio with a name, optional description, and base currency.
- The system must let the user list all portfolios.
- The system must let the user update portfolio metadata.
- The system must let the user delete a portfolio and its related data after explicit confirmation.
- The system must prevent data from one portfolio from appearing in another portfolio.

### FR-2 Balance Management

- The system must let the user create one or more balance records inside a portfolio.
- Each balance must include a label and amount in the portfolio base currency.
- The system must let the user list, update, and delete balances within the current portfolio.
- The system must keep balance records isolated by portfolio.

### FR-3 Manual Position Management

- The system must let the user create a stock position manually.
- Each position must contain at least a symbol, quantity, and average cost in the portfolio base currency.
- The system must let the user list, update, and delete positions within the current portfolio.
- The system must maintain one aggregate position per symbol per portfolio.

### FR-4 Position CSV Import

- The system must let the user upload a CSV file to import positions into a selected portfolio.
- The CSV import must support a simple position snapshot format with required columns `symbol`, `quantity`, and `average_cost`, plus optional `name`.
- The system must validate file type, required headers, numeric values, and duplicate symbols before applying changes.
- The system must show row-level validation errors before commit.
- The import behavior must be `upsert by symbol` within the selected portfolio.

### FR-5 Market Data

- The system must fetch delayed market data from a public datasource.
- The system must expose the latest available indicative price for a symbol.
- The system must show quote freshness or as-of information.
- The system must keep core portfolio CRUD available even if market data is unavailable.

### FR-6 Simulated Trading Operations

- The system must let the user submit a simulated `BUY` or `SELL` operation for a portfolio.
- A trading operation must include symbol, side, quantity, price, commission, trade date/time, and the balance record used for settlement.
- For a `BUY`, the system must decrease the selected balance by `quantity * price + commission`.
- For a `SELL`, the system must increase the selected balance by `quantity * price - commission`.
- The system must update the aggregate portfolio position using average-cost logic.
- The system must reject any trading operation that would cause the selected balance to become negative.
- The system must reject a sell quantity greater than the currently held quantity.
- The system must not implement FIFO.

### FR-7 Read Views

- The system must provide a portfolio summary view that shows balances, positions, and recent trading operations.
- The system must provide a simple quote view for symbols in the active portfolio.
- The system must clearly mark market values as indicative.

## Non-Functional Requirements

- Frontend stack: Vite, React, shadcn.
- Backend stack: Python, FastAPI.
- Database: PostgreSQL.
- Monetary and quantity values must use decimal-safe storage and API contracts.
- The backend must return structured validation errors for bad input.
- Every persisted record must include `created_at` and `updated_at` timestamps where applicable.
- API behavior must stay simple REST over HTTP.

## Acceptance Criteria

- A user can create two portfolios and confirm that their positions, balances, and trading operations stay isolated.
- A user can create, edit, and delete manual positions without affecting other portfolios.
- A user can upload a valid CSV file, review validation output, and commit the import successfully.
- A user receives row-level error details for an invalid CSV file.
- A user can create, edit, and delete balances in a portfolio.
- A user can submit a simulated buy operation and see both the position and selected balance update immediately.
- A user can submit a simulated sell operation that reduces quantity and increases balance while rejecting oversell attempts.
- A user cannot submit a trading operation when the resulting selected balance would be negative.
- A user can view delayed quote data with freshness metadata, and the app still works when quote retrieval fails.
