# Requirements Document

## Purpose

Define the live product requirements for Ledger as shipped today. This release is a trusted single-user portfolio tracker with text-template rendering, not a stock-analysis platform.

## Product Scope

### In Scope

- Portfolio CRUD with strict isolation between portfolios.
- Balance CRUD inside a portfolio, including `DEPOSIT` and `WITHDRAWAL` balance types.
- Manual position CRUD inside a portfolio.
- Position import by CSV upload with preview-before-commit.
- Delayed quote and price-history retrieval for symbols in a portfolio.
- Simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations.
- Global text-template CRUD plus placeholder browsing and compile preview.
- Report generation from templates, markdown upload, slug-based report CRUD, and markdown download.

### Out Of Scope

- Authentication, authorization, or multi-tenant access control.
- Realtime quotes, websocket streaming, broker connectivity, or live order routing.
- Stock-analysis conversations, snippets, responses, versions, or provider orchestration.
- Scheduling, alerts, notifications, or autonomous loops.
- Tax lots, FIFO, realized tax reporting, or accounting exports.

## Operating Assumptions

- Ledger runs in a trusted environment because there is no login layer.
- Each portfolio is an isolated workspace with its own balances, positions, operations, and quote lookups.
- A portfolio has one base currency. Balances, positions, prices, and simulated operations use that currency in the current release.
- Market data is delayed and indicative; it never becomes the source of truth for balances or positions.
- Local database records are authoritative for current portfolio state, saved templates, and persisted reports.

## Functional Requirements

### FR-1 Portfolio Management

- The system must let the user create a portfolio with `name`, `slug`, optional `description`, and `baseCurrency`.
- Portfolio slugs must be lowercase underscore identifiers and unique across the system.
- The system must let the user list all portfolios with `positionCount` and `balanceCount` summary fields.
- The system must let the user update portfolio `name` and `description`.
- The update contract must not allow changing the slug.
- Deleting a portfolio must cascade to its balances, positions, and trading operations.

### FR-2 Balance Management

- The system must let the user create, list, update, and delete balances within a portfolio.
- Each balance must include `label`, `amount`, and `operationType`.
- `operationType` must be either `DEPOSIT` or `WITHDRAWAL`.
- Balance labels must be unique within a portfolio.
- Balance amounts must be greater than or equal to zero.
- If a balance already has trading history, its `operationType` must not be changed.

### FR-3 Position Management

- The system must let the user create, list, update, and delete positions within a portfolio.
- Each position must include at least `symbol`, `quantity`, and `averageCost`; `name` is optional.
- Symbols must be normalized to uppercase.
- Quantity must be greater than zero.
- Average cost must be greater than or equal to zero.
- The system must maintain at most one aggregate position per `(portfolio, symbol)`.
- If the user omits a position name, the backend may attempt symbol-name enrichment through the quote provider and cache successful results.

### FR-4 Position CSV Import

- The system must expose separate preview and commit endpoints for CSV import.
- CSV input must be UTF-8 text and either have a `.csv` extension or `text/csv` content type.
- Required headers are `symbol`, `quantity`, and `average_cost`; optional header is `name`.
- Unsupported headers must be rejected.
- Duplicate symbols inside a single file must be reported as row errors.
- Preview must return `acceptedRows` plus row-level `errors` without mutating data.
- Commit must reject the file when any validation errors remain.
- Commit behavior must be `upsert by symbol` within the selected portfolio.
- Commit must be atomic.

### FR-5 Simulated Trading Operations

- The system must let the user submit `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations for a portfolio.
- `BUY`, `SELL`, and `DIVIDEND` must reference a deposit balance via `balanceId`.
- `SPLIT` must not require a balance.
- `BUY` must decrease the selected balance by `quantity * price + commission`.
- `SELL` must increase the selected balance by `quantity * price - commission`.
- `DIVIDEND` must increase the selected balance by `dividendAmount - commission` and must not change position quantity or average cost.
- `SPLIT` must multiply position quantity by `splitRatio`, divide average cost by the same ratio, and must not change cash.
- The system must reject a trade when the selected balance would become negative.
- The system must reject a buy when total portfolio cash is insufficient after considering withdrawal balances.
- The system must reject a sell quantity greater than current holdings.
- The system must reject dividends and splits when no position exists for the symbol.
- Trading operations must remain append-only historical records.

### FR-6 Market Data

- The system must fetch delayed indicative quotes for requested symbols in portfolio context.
- Quote requests must accept comma-separated symbols and ignore duplicates or blank entries.
- Quote responses must include `warnings` for unavailable quotes, cached fallback, or currency mismatch.
- Successful quote responses must include `price`, `currency`, `provider`, `asOf`, `isStale`, optional `previousClose`, and optional `name`.
- The system must expose recent price-history series for supported ranges `1mo`, `3mo`, `ytd`, `1y`, and `max`.
- History failures for one symbol must degrade to warnings rather than failing the whole response.

### FR-7 Template Management And Compile

- The system must let the user create, list, read, update, and delete global text templates.
- Template names must be unique.
- Templates must store plain `name` and `content`; there is no multi-step template mode in the live product.
- The system must expose a placeholder tree that lists live portfolio slugs and positions.
- The system must expose an inline compile endpoint that accepts ad hoc content and returns compiled output.
- The system must expose a stored-template compile endpoint by template id.
- Placeholder resolution must support the `portfolios.<slug>...` and `reports.<name>...` namespaces.
- `reports.<name>.content` must re-compile stored report content so embedded placeholders resolve against current live data.
- Report-content recursion must detect circular references and render an explicit sentinel instead of looping.
- The placeholder tree must expose live reports with `name` and `createdAt` in addition to portfolio data.
- Unknown roots, portfolios, or fields must compile to explicit sentinel strings such as `[Unknown portfolio: ...]` instead of silently disappearing.

### FR-8 Report Management

- The system must let the user list, read, update, delete, and download reports by `slug`.
- The system must let the user create a compiled report by posting a stored template id.
- Compiled report creation must normalize the template name to snake_case, append a UTC timestamp, and use that value for both `name` and `slug`.
- If two compiled reports collide within the same second, the system must append `_2`, `_3`, and so on until the name/slug is unique.
- The system must let the user upload a UTF-8 markdown file smaller than 2 MB to create a report.
- Uploads must reject non-`.md` filenames, invalid encodings, and empty files.
- Uploaded reports must store `source="uploaded"`; compiled reports must store `source="compiled"`.
- Uploaded reports may include optional `author`, `description`, and comma-separated `tags` metadata.
- Report update payloads must allow editing `content` only; `name`, `slug`, `source`, and metadata are immutable after creation.
- Downloads must return the stored markdown content as `text/markdown` with `Content-Disposition: attachment; filename="{slug}.md"`.

## Non-Functional Requirements

- Frontend stack: React 19, Vite, TanStack Query 5, React Router 7, shadcn/ui, Vitest, Playwright.
- Backend stack: Python 3.13, FastAPI, SQLAlchemy, Pydantic.
- Database runtime and tests must use PostgreSQL.
- Monetary and quantity values must use decimal-safe storage and API contracts.
- External JSON must stay camelCase and timestamps must serialize as ISO 8601 UTC strings.
- The backend must return structured validation or business-rule errors for bad input.
- The product must degrade gracefully when quote-provider calls fail by preserving truthful local state.

## Acceptance Criteria

- A user can create two portfolios and confirm that balances, positions, and trades stay isolated.
- A user can create deposit and withdrawal balances and see withdrawal balances reduce computed cash totals.
- A user can upload a valid CSV file, review preview output, and commit successfully.
- A user receives row-level error details for an invalid CSV file.
- A user can submit `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations and see balance and position state update immediately.
- A user cannot submit an operation when it would overdraw cash, oversell holdings, or target a missing position.
- A user can view delayed quotes and price history with warnings, and the app still works when quote retrieval fails.
- A user can create or edit a template, browse placeholders, and compile live portfolio text successfully.
- A user can generate a report from a template, upload a markdown report with metadata, edit report content, and download the report by slug.
- A template can reference `reports.<name>.content` and receive circular-reference sentinels instead of infinite recursion.
