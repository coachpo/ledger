# Requirements Document

## Purpose

Define the product, workflow, and contract requirements for Ledger as the canonical documentation set. The current release covers a trusted single-user portfolio tracker plus a stock-scoped advisory analysis system backed by configurable LLM providers.

## Product Scope

### In Scope

- Portfolio CRUD with strict isolation between portfolios.
- Manual balance CRUD inside a portfolio.
- Manual position CRUD inside a portfolio.
- Position import by CSV upload with preview-before-commit.
- Delayed quote and price-history retrieval for symbols in a portfolio.
- Simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations.
- Per-portfolio stock-analysis enablement and defaults.
- App-global LLM config CRUD.
- App-global prompt template CRUD and preview.
- Stock-analysis conversations, runs, requests, responses, and version history.
- Advisory-only structured outputs that separate fresh analysis, comparison, decision, and reflection.

### Out Of Scope

- User authentication, authorization, or multi-tenant access control.
- Realtime quotes, websocket streaming, or broker connectivity.
- Automatic trade execution based on model output.
- Portfolio-scope analysis as a current release feature.
- Multi-provider fan-out or concurrency planning within a single run.
- Scheduling, autonomous loop chaining, alerts, or notifications.
- External news, filings, or research ingestion beyond existing app context and user-supplied notes.
- FIFO, tax lots, realized tax reporting, or accounting exports.

## Operating Assumptions

- Ledger runs in a trusted environment because there is no login layer.
- Each portfolio is an isolated workspace with its own balances, positions, operations, and stock-analysis history.
- A portfolio has one base currency. Balances, positions, prices, and simulated operations use that currency in the current release.
- Market data is delayed and indicative; it assists display and analysis but never becomes the source of truth for balances or positions.
- Stock analysis is disabled by default per portfolio until the user enables it explicitly.
- Each stock-analysis run uses exactly one enabled LLM config.
- Local database records are authoritative for history, replay, and audits even if a provider later loses retention or becomes unavailable.

## Functional Requirements

### FR-1 Portfolio Management

- The system must let the user create a portfolio with a name, optional description, and base currency.
- The system must let the user list all portfolios.
- The system must let the user update portfolio metadata.
- The system must let the user delete a portfolio and all related balances, positions, operations, and stock-analysis records after explicit confirmation.
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
- The CSV import must support required columns `symbol`, `quantity`, and `average_cost`, plus optional `name`.
- The system must validate file type, required headers, numeric values, and duplicate symbols before applying changes.
- The system must show row-level validation errors before commit.
- The import behavior must be `upsert by symbol` within the selected portfolio.
- Commit must be atomic: either all validated rows apply or none do.

### FR-5 Market Data And History

- The system must fetch delayed market data from a public datasource.
- The system must expose the latest available indicative quote for requested symbols.
- The system must expose recent price-history series for requested symbols and supported ranges.
- The system must show quote freshness and return warnings when quote or history data is unavailable.
- The system must keep core portfolio CRUD and stock-analysis history available even if market data is unavailable.

### FR-6 Simulated Trading Operations

- The system must let the user submit simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations for a portfolio.
- Every operation must include the selected balance record, symbol, operation side, and execution timestamp.
- `BUY` must also include quantity, price, and optional commission.
- `SELL` must also include quantity, price, and optional commission.
- `DIVIDEND` must also include `dividend_amount` and optional commission.
- `SPLIT` must also include `split_ratio`.
- For a `BUY`, the system must decrease the selected balance by `quantity * price + commission`.
- For a `SELL`, the system must increase the selected balance by `quantity * price - commission`.
- For a `DIVIDEND`, the system must increase the selected balance by `dividend_amount - commission` and must not change position quantity or average cost.
- For a `SPLIT`, the system must require an existing position, multiply the position quantity by `split_ratio`, divide average cost by the same ratio, and must not change balance cash.
- The system must reject any operation that would cause the selected balance to become negative.
- The system must reject a sell quantity greater than the currently held quantity.
- The system must reject a split when no position exists for the selected symbol.
- Trading operations must remain append-only historical records.

### FR-7 Portfolio Read Views

- The system must provide a portfolio summary view that shows balances, positions, recent trading operations, and delayed market context.
- The system must clearly mark market values and market history as indicative.
- The system must let the user navigate from portfolio state to stock-analysis actions without leaving portfolio context.

### FR-8 Portfolio Stock-Analysis Settings

- The system must expose one stock-analysis settings record per portfolio.
- The settings record must support enabling or disabling stock analysis for that portfolio.
- The settings record must support optional default LLM config and default prompt template selections.
- The settings record must support a `compareToOrigin` default that later runs can override.
- The backend must reject new runs when stock analysis is disabled for the selected portfolio.

### FR-9 LLM Config Management

- The system must let the user create, read, update, list, and delete reusable LLM configs.
- Supported providers must be `openai`, `anthropic`, and `gemini`.
- OpenAI configs must require an endpoint mode of `chat_completions` or `responses`.
- Non-OpenAI configs must reject an OpenAI endpoint mode.
- API keys must be stored server-side and must not be returned in plaintext on reads.
- A referenced config must become disabled instead of being hard-deleted.
- Each run must use exactly one enabled LLM config.

### FR-10 Prompt Template Management And Preview

- The system must let the user create, read, update, list, and delete reusable prompt templates.
- Each template must carry separate text for the `fresh_analysis` and `compare_decide_reflect` steps.
- The system must support ad hoc prompt overrides for one-off runs.
- The system must expose preview endpoints that render prompt text against live portfolio context without calling an LLM provider.
- Preview must fail when placeholders are invalid, out of scope, or unresolved against the current step context.
- Templates used by historical requests must remain readable even after later edits.
- A used template must archive instead of being hard-deleted.

### FR-11 Stock-Analysis Conversations

- The system must let the user create, list, read, and update stock-analysis conversations within a portfolio.
- Each conversation must belong to exactly one `(portfolio, symbol)` pair.
- Symbols must be normalized to uppercase.
- Conversation listing must support filtering by symbol and archived state.
- Conversations must support soft archival rather than destructive delete in the current release.

### FR-12 Stock-Analysis Runs

- The system must let the user create queued runs for an existing stock-analysis conversation.
- Supported run types must be `initial_review`, `periodic_review`, `event_review`, and `manual_follow_up`.
- A review-bearing run must execute the `fresh_analysis` step before the `compare_decide_reflect` step.
- The fresh-analysis step must default to current context only and must not inject prior thesis text by default.
- The compare step must use locally persisted context, prior version references, and the parsed fresh-analysis payload.
- The system must persist request records before each outbound provider call.
- The system must expose explicit run execution status transitions including `queued`, `running`, `completed`, `partial_failure`, and `failed`.
- The current release must not fan out a single run to multiple providers or multiple configs.

### FR-13 Structured Output And Versioning

- The system must require machine-readable structured output for successful analysis parsing.
- The final review model must separate `freshAnalysis`, `comparison`, `decision`, and `reflection` sections.
- The comparison section must classify changes using one of: `new_fact`, `changed_interpretation`, `corrected_mistake`, `noise`, `thesis_strengthening`, `thesis_weakening`, or `thesis_breaking`.
- The decision section must include an explicit action, reason, and reversal conditions.
- The reflection section must capture what was right, what was missed, and whether the conclusion still holds from a blank-page check.
- A new version snapshot must be created only when the final structured response parses successfully.
- Historical versions must remain immutable after creation.

### FR-14 Audit History, Replay, And Local Authority

- The system must persist context snapshots, rendered prompts, placeholder maps, outbound payload snapshots without secrets, raw provider payloads, parsed payloads, and version snapshots.
- The system must keep local history readable even if provider-side retention later expires.
- History and viewer rendering must use stored local snapshots rather than re-rendering from live template revisions.
- Parse failures and partial failures must remain visible in history rather than being silently dropped.
- The system must never trigger trading-operation creation from stock-analysis output.

## Non-Functional Requirements

- Frontend stack: Vite, React, TanStack Query, shadcn.
- Backend stack: Python, FastAPI, SQLAlchemy, Pydantic.
- Database: PostgreSQL in production-style runtime, SQLite-supported for local use and tests.
- Monetary and quantity values must use decimal-safe storage and API contracts.
- External JSON must stay camelCase and timestamps must serialize as ISO 8601 UTC strings.
- The backend must return structured validation or business-rule errors for bad input.
- LLM provider secrets must stay server-side only.
- Prompt preview and execution must use the same rendering logic.
- Requests, responses, and versions must be immutable after creation except for in-flight status and parse metadata transitions.
- The product must degrade gracefully when quote providers or LLM providers fail by preserving truthful local state.

## Acceptance Criteria

- A user can create two portfolios and confirm that balances, positions, operations, and stock-analysis history stay isolated.
- A user can create, edit, and delete balances and positions without affecting other portfolios.
- A user can upload a valid CSV file, review validation output, and commit the import successfully.
- A user receives row-level error details for an invalid CSV file.
- A user can submit simulated `BUY` and `SELL` operations and see both the selected balance and aggregate position update immediately.
- A user can submit a `DIVIDEND` operation and see cash credited without changing quantity or average cost.
- A user can submit a `SPLIT` operation and see quantity and average cost adjust while cash remains unchanged.
- A user cannot submit an operation when the resulting balance would be negative, a sell would overshoot holdings, or a split targets a missing position.
- A user can view delayed quotes and price history with warnings and freshness metadata, and the app still works when market-data retrieval fails.
- A user can enable stock analysis for a portfolio, assign defaults, and later disable it again.
- A user can create or edit an LLM config and prompt template, preview the rendered prompt for a selected stock, and submit a run successfully.
- An `initial_review` followed by a later `periodic_review` for the same symbol produces a version timeline with structured deltas.
- Invalid placeholders, cross-portfolio references, and missing prompt context are rejected before provider execution.
- Historical runs continue to display their original rendered prompts and parsed outputs after later template edits or archival.
- Final outputs always remain advisory and never mutate balances, positions, or trading operations.
