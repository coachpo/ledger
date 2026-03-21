# Data Model Design

> Status: Current live-code reference as of 2026-03-21 (`8fd7fee`).

## Overview

Ledger uses a relational schema centered on isolated portfolios. Live persistence covers portfolios, balances, positions, trading operations, backtests, cached market quotes, symbol-name cache rows, global text templates, and persisted markdown reports.

Legacy stock-analysis tables from older builds are not part of the live schema contract; `init_db()` drops them during supported upgrade paths.

## Entity Relationship Summary

- One `portfolio` has many `balances`.
- One `portfolio` has many `positions`.
- One `portfolio` has many `trading_operations`.
- One `portfolio` has many `backtests`.
- One `trading_operation` may reference one `balance`, but keeps `balance_label` as a historical snapshot.
- One `trading_operation` may reference one `backtest` for simulated-trade attribution.
- `market_quotes` are shared cache rows keyed by provider and symbol metadata.
- `symbol_name_cache` is a global cache keyed by symbol.
- `text_templates` are global reusable documents.
- `reports` are global markdown snapshots keyed by both `name` and `slug`.

## Tables

### portfolios

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `name` | varchar(100) | No | User-facing portfolio name |
| `slug` | varchar(100) | No | Unique lowercase underscore identifier |
| `description` | text | Yes | Optional description |
| `base_currency` | char(3) | No | ISO-like 3-letter code |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints and indexes:

- Unique constraint on `slug`
- Index on `name`

### balances

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `portfolio_id` | integer | No | FK to `portfolios.id` |
| `label` | varchar(60) | No | Example: `Broker Cash`, `Reserve` |
| `operation_type` | varchar | No | `DEPOSIT` or `WITHDRAWAL` |
| `amount` | numeric(20,4) | No | Decimal-safe cash amount |
| `currency` | char(3) | No | Mirrors portfolio base currency |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints and indexes:

- Unique `(portfolio_id, label)`
- Check `amount >= 0`
- Index `(portfolio_id, label)`

Behavior notes:

- Withdrawal balances are stored as non-negative rows; the sign is applied in portfolio cash calculations.
- A balance may be deleted after use in trading history because operation rows preserve `balance_label` and `balance_id` uses `ON DELETE SET NULL`.

### positions

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `portfolio_id` | integer | No | FK to `portfolios.id` |
| `symbol` | varchar(32) | No | Uppercase ticker symbol |
| `name` | varchar(120) | Yes | Optional display name |
| `quantity` | numeric(20,8) | No | Aggregate units held |
| `average_cost` | numeric(20,8) | No | Aggregate average cost basis |
| `currency` | char(3) | No | Matches portfolio base currency |
| `last_source` | varchar(16) | No | `manual`, `csv`, or `simulation` |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints:

- Unique `(portfolio_id, symbol)`
- Check `quantity > 0`
- Check `average_cost >= 0`

### trading_operations

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `portfolio_id` | integer | No | FK to `portfolios.id` |
| `balance_id` | integer | Yes | FK to `balances.id`; nullable for preserved history |
| `backtest_id` | integer | Yes | FK to `backtests.id`; null for manual trades |
| `balance_label` | varchar(60) | No | Snapshot of selected balance label |
| `symbol` | varchar(32) | No | Uppercase ticker symbol |
| `side` | varchar(10) | No | `BUY`, `SELL`, `DIVIDEND`, or `SPLIT` |
| `quantity` / `price` | numeric | Yes | Used for `BUY` and `SELL` |
| `commission` | numeric(20,4) | No | Absolute fee amount |
| `dividend_amount` | numeric(20,4) | Yes | Used for `DIVIDEND` |
| `split_ratio` | numeric(10,6) | Yes | Used for `SPLIT` |
| `currency` | char(3) | No | Portfolio base currency snapshot |
| `executed_at` | timestamptz | No | User-provided timestamp |
| `created_at` | timestamptz | No | Persistence timestamp |

Constraints and indexes:

- Check `side IN ('BUY', 'SELL', 'DIVIDEND', 'SPLIT')`
- Check `quantity > 0`
- Check `price >= 0`
- Check `commission >= 0`
- Index `(portfolio_id, executed_at)`
- Index `(portfolio_id, symbol)`

### backtests

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `portfolio_id` | integer | No | FK to `portfolios.id` |
| `deposit_balance_id` | integer | No | FK to `balances.id`, selected cash source |
| `template_id` | integer | No | FK to `text_templates.id` |
| `name` | varchar(200) | No | User-facing run label |
| `status` | varchar(20) | No | `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, or `CANCELLED` |
| `frequency` | varchar(10) | No | `DAILY`, `WEEKLY`, or `MONTHLY` |
| `start_date` / `end_date` | date | No | Historical simulation window |
| `current_cycle_date` | date | Yes | Active progress marker |
| `total_cycles` / `completed_cycles` | integer | No | Progress counters |
| `llm_base_url` / `llm_api_key` / `llm_model` | varchar | No | Per-run LLM connection settings |
| `price_mode` | varchar(20) | No | `CLOSING_PRICE` or `LLM_DECIDED` |
| `llm_price_success_rate` | numeric(5,4) | Yes | Probability-like fraction for LLM-decided execution |
| `commission_mode` | varchar(20) | No | `ZERO`, `FIXED`, or `PERCENTAGE` |
| `commission_value` | numeric(18,8) | No | Commission amount or fraction |
| `benchmark_symbols` | jsonb | No | Ordered list of benchmark tickers |
| `recent_activity` | jsonb | Yes | Recent cycle summaries for running-state UI |
| `results` | jsonb | Yes | Completed result payload with metrics, curves, and trades |
| `error_message` | text | Yes | Terminal failure details |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints and indexes:

- Index on `portfolio_id`
- Index on `status`

### market_quotes

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `symbol` | varchar(32) | No | Quote symbol |
| `provider` | varchar(50) | No | Quote source identifier |
| `price` | numeric(20,8) | No | Latest delayed price |
| `previous_close` | numeric(20,8) | Yes | Previous close when available |
| `currency` | char(3) | No | Quote currency |
| `name` | varchar(255) | Yes | Optional issuer/company name |
| `as_of` | timestamptz | Yes | Provider timestamp |
| `fetched_at` | timestamptz | No | Local cache fetch time |
| `is_stale` | boolean | No | Cached staleness flag |

Constraints and indexes:

- Unique `(provider, symbol, as_of)`
- Index `(symbol, fetched_at)`
- Index `(provider, symbol)`

### symbol_name_cache

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `symbol` | varchar(32) | No | Normalized symbol |
| `name` | varchar(255) | No | Cached company name |
| `fetched_at` | timestamptz | No | Cache insertion time |

Constraints and indexes:

- Unique `symbol`
- Index `fetched_at`
- Table prefix `UNLOGGED` because the cache is rebuildable

### text_templates

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `name` | varchar(100) | No | Unique template name |
| `content` | text | No | Raw template body |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints:

- Unique `name`

### reports

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | integer | No | Primary key |
| `name` | varchar(200) | No | Unique display name for the report |
| `slug` | varchar(200) | No | Unique route/download identifier |
| `source` | varchar(20) | No | `compiled`, `uploaded`, or `external` |
| `content` | text | No | Stored markdown content |
| `metadata` | jsonb | No | Extensible metadata object with known `author`, `description`, `tags`, and optional `analysis` keys used by filtered report retrieval |
| `created_at` / `updated_at` | timestamptz | No | Timestamps from mixin |

Constraints:

- Unique `name`
- Unique `slug`

## Derived Values And Read-Time Rules

- Portfolio cash is derived from balances: deposits add, withdrawals subtract.
- Position market value is calculated at read time only when quote currency matches portfolio base currency.
- Market history series are fetched on demand and are not persisted as first-class rows.
- Template compile output is derived from current portfolios, balances, and positions at compile time.
- Report content is persisted, but `{{reports.<name>.content}}` re-compiles the stored markdown when embedded through the template system.

## Data Integrity Rules

- All portfolio-owned tables enforce portfolio isolation through `portfolio_id`.
- Balances, positions, and trading operations use the portfolio base currency in the current release.
- Trading-operation balance and position changes commit in one transaction.
- Backtest rows persist per-run configuration plus terminal result payloads; simulated trades are still written to `trading_operations` for attribution and cleanup.
- CSV import commit updates positions atomically.
- Cached quotes and symbol-name cache rows are reconstructible and must not be treated as authoritative user data.
- Reports are global documents with immutable `name`, `slug`, `source`, and metadata after creation; only `content` is editable.
- Direct JSON-created reports use `source="external"` and follow the same slug-addressed lifecycle as compiled and uploaded reports.
- Canonical report list filters read from `metadata.analysis.ticker`, `metadata.analysis.reviewType`, `metadata.analysis.portfolioSlug`, top-level `metadata.tags`, and `source`.
- Backtest-generated reports are tagged with `backtest_<id>` in `metadata.tags`, and startup repair rewrites interrupted `PENDING` or `RUNNING` backtests to `FAILED`.

## Suggested Enums

- `balances.operation_type`: `DEPOSIT`, `WITHDRAWAL`
- `positions.last_source`: `manual`, `csv`, `simulation`
- `trading_operations.side`: `BUY`, `SELL`, `DIVIDEND`, `SPLIT`
- `backtests.status`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`
- `backtests.frequency`: `DAILY`, `WEEKLY`, `MONTHLY`
- `backtests.price_mode`: `CLOSING_PRICE`, `LLM_DECIDED`
- `backtests.commission_mode`: `ZERO`, `FIXED`, `PERCENTAGE`
- `reports.source`: `compiled`, `uploaded`, `external`

## Lifecycle Notes

- Trading operations remain append-only for auditability.
- Full sell-down deletes the corresponding position row.
- Quote cache rows may be refreshed or cleaned without affecting portfolio records.
- Legacy stock-analysis tables are removed by supported DB upgrade logic and should not be reintroduced casually.
- Reports survive template deletion because there is intentionally no foreign key back to `text_templates`.
