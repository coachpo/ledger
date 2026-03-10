# Data Model Design

## Overview

The MVP uses a small relational schema centered on isolated portfolios. Portfolio-owned entities store current balances, aggregate positions, and append-only trading operations. Market quotes are cached separately because they come from external public providers.

## Entity Relationship Summary

- One `portfolio` has many `balances`.
- One `portfolio` has many `positions`.
- One `portfolio` has many `trading_operations`.
- `market_quotes` are shared reference data keyed by symbol and provider.

## Tables

### portfolios

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| name | varchar(100) | No | User-facing portfolio name |
| description | text | Yes | Optional description |
| base_currency | char(3) | No | ISO 4217 code |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`

Indexes:

- Index on `name`

### balances

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| portfolio_id | uuid | No | FK to `portfolios.id` |
| label | varchar(60) | No | Example: `Cash`, `Reserve` |
| amount | numeric(20, 4) | No | Decimal-safe cash amount |
| currency | char(3) | No | Must match portfolio base currency |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Unique: `(portfolio_id, label)`
- Check: `amount >= 0`

Indexes:

- Index on `(portfolio_id, label)`

### positions

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| portfolio_id | uuid | No | FK to `portfolios.id` |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| name | varchar(120) | Yes | Optional display name |
| quantity | numeric(20, 8) | No | Aggregate units held |
| average_cost | numeric(20, 8) | No | Aggregate average cost basis |
| currency | char(3) | No | Must match portfolio base currency |
| last_source | varchar(16) | No | `manual`, `csv`, or `simulation` |
| created_at | timestamptz | No | Creation timestamp |
| updated_at | timestamptz | No | Last update timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Unique: `(portfolio_id, symbol)`
- Check: `quantity > 0`
- Check: `average_cost >= 0`

Indexes:

- Unique index on `(portfolio_id, symbol)`

### trading_operations

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| portfolio_id | uuid | No | FK to `portfolios.id` |
| balance_id | uuid | Yes | FK to `balances.id`, nullable for preserved history |
| balance_label | varchar(60) | No | Snapshot of selected balance label |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| side | varchar(4) | No | `BUY` or `SELL` |
| quantity | numeric(20, 8) | No | Units traded |
| price | numeric(20, 8) | No | Per-unit simulated execution price |
| commission | numeric(20, 4) | No | Absolute fee amount |
| currency | char(3) | No | Must match portfolio base currency |
| executed_at | timestamptz | No | User-provided execution timestamp |
| created_at | timestamptz | No | Persistence timestamp |

Constraints:

- Primary key: `id`
- Foreign key: `portfolio_id -> portfolios.id` with `ON DELETE CASCADE`
- Foreign key: `balance_id -> balances.id` with `ON DELETE SET NULL`
- Check: `side IN ('BUY', 'SELL')`
- Check: `quantity > 0`
- Check: `price >= 0`
- Check: `commission >= 0`

Indexes:

- Index on `(portfolio_id, executed_at desc)`
- Index on `(portfolio_id, symbol)`

### market_quotes

| Column | Type | Null | Notes |
|---|---|---|---|
| id | uuid | No | Primary key |
| symbol | varchar(32) | No | Uppercase ticker symbol |
| provider | varchar(50) | No | Public datasource identifier |
| price | numeric(20, 8) | No | Latest delayed price |
| currency | char(3) | No | Quote currency |
| as_of | timestamptz | Yes | Provider quote timestamp when available |
| fetched_at | timestamptz | No | Local cache fetch time |
| is_stale | boolean | No | Staleness indicator |

Constraints:

- Primary key: `id`
- Unique: `(provider, symbol, as_of)`

Indexes:

- Index on `(symbol, fetched_at desc)`
- Index on `(provider, symbol)`

## Derived Values

- Position market value is calculated only when quote currency matches the portfolio base currency.
- Portfolio cash total = sum of `balances.amount` for the selected portfolio

Derived values are calculated at read time and are not stored as separate columns in MVP.

## Data Integrity Rules

- All portfolio-owned tables must enforce portfolio isolation through `portfolio_id`.
- Balances, positions, and trading operations must use the portfolio base currency in MVP.
- A trading operation must update `balances` and `positions` inside one database transaction.
- CSV import commit must update `positions` inside one database transaction.

## Suggested Enums

- `positions.last_source`: `manual`, `csv`, `simulation`
- `trading_operations.side`: `BUY`, `SELL`

## Persistence Notes

- Trading operations remain append-only for auditability of simulated actions.
- Positions store only the current aggregate holding state, not tax lots.
- Current balances and positions are authoritative after manual edits, CSV imports, and simulated trades.
- Market quotes are cache records and may be overwritten or cleaned up by retention jobs without affecting portfolio records.
