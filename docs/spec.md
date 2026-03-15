# Technical Specification

## Overview

This specification defines Ledger as an auth-less portfolio application with two integrated capabilities:

- portfolio tracking and simulation for balances, positions, market context, and manual operations;
- stock-scoped advisory analysis that uses configurable LLM providers while keeping local history authoritative.

The current stock-analysis surface is stock-only and centered on prompt preview, reusable prompt resources, stored responses, and version history. Historical run/request rows remain part of the persisted data model, but the live run create/execute surface is not exposed in the current release.

## Explicit Scope Boundaries

- Stock analysis is scoped to one `(portfolio, symbol)` conversation.
- Each run uses one enabled provider at a time.
- The current release does not support portfolio-scope analysis.
- The current release does not support multi-provider fan-out, dispatch planning, or concurrency caps per run.
- Provider-side conversation or thread objects are not the source of truth.
- Automatic trading, scheduling, and external research ingestion remain out of scope.

## Architecture

### Frontend

- React + Vite application.
- TanStack Query for API-backed client state.
- shadcn components for forms, dialogs, tabs, tables, alerts, and status callouts.
- Portfolio workspace surfaces balances, positions, operations, market context, and stock analysis from one navigation model.
- Shared API contracts and query keys live in `frontend/src/lib/api.ts` and `frontend/src/lib/query-keys.ts`.

### Backend

- FastAPI REST API with thin routers and service-owned business rules.
- SQLAlchemy models and repositories for persistence.
- Pydantic read/write contracts with camelCase external JSON.
- Stock-analysis orchestration split across dedicated services for context building, prompt rendering, provider dispatch, parsing, and version materialization.

### Provider Boundary

- Supported providers are OpenAI, Anthropic, and Gemini.
- OpenAI configs select `chat_completions` or `responses` per config.
- Prompt rendering is provider-neutral and always produces canonical `instructions` and `input` strings before adapter-specific payload assembly.
- Provider adapters are responsible for structured-output controls, request-shape translation, usage extraction, and provider identifiers.
- Provider-side storage is optional debug support only; local rows remain authoritative.

### Database

- Relational schema with portfolio-scoped resources.
- Decimal-safe numeric columns for money, quantity, prices, dividends, and split ratios.
- JSON columns for analysis snapshots, parsed payloads, and structured version sections.
- Referential integrity and explicit archival rules for analysis resources.

## Domain Model Rules

### Portfolio Isolation

- All portfolio-owned records carry `portfolio_id`.
- Reads and writes always scope through the active portfolio.
- No balance, position, operation, or stock-analysis conversation can cross portfolio boundaries.

### Balances

- A balance represents available cash within a portfolio.
- Currency is derived from the portfolio base currency.
- Amount must be greater than or equal to zero.

### Positions

- A position is the aggregate holding for one symbol in one portfolio.
- Symbols are normalized to uppercase.
- Quantity must be greater than zero.
- Average cost must be greater than or equal to zero.
- Only one active position per `(portfolio_id, symbol)` is allowed.

### Trading Operations

- Trading operations are append-only simulated events.
- Supported sides are `BUY`, `SELL`, `DIVIDEND`, and `SPLIT`.
- Each operation records the current `balance_id` plus a `balance_label` snapshot for historical readability.
- Current balances and positions remain the source of truth for portfolio state; operations are the simulation log.

#### Operation Rules

- `BUY`: decrease cash by `quantity * price + commission`; update or create the aggregate position using average-cost logic.
- `SELL`: increase cash by `quantity * price - commission`; reject oversell; delete the position on full sell-down; preserve average cost on partial sell.
- `DIVIDEND`: increase cash by `dividend_amount - commission`; do not change position quantity or average cost.
- `SPLIT`: require an existing position; multiply quantity by `split_ratio`; divide average cost by the same ratio; do not move cash.

### Market Data

- Market data is external and non-authoritative.
- Quote and history endpoints are best-effort and may return warnings.
- Quote responses include freshness and provider metadata.
- History responses return range, interval, and multiple symbol series when requested.

### Stock Analysis Settings

- Each portfolio owns one stock-analysis settings record.
- Analysis is disabled by default until explicitly enabled.
- Settings can define default prompt template and default `compareToOrigin` behavior.

### Stock Analysis Conversations

- A conversation belongs to one portfolio and one symbol.
- Conversations are the app-level container for runs and versions.
- Conversations support soft archival instead of destructive delete.

### Stock Analysis Runs

- A run belongs to one conversation.
- A run declares `mode` as `single_prompt` or `two_step_workflow`.
- Runs can be `queued`, `running`, `completed`, `partial_failure`, or `failed`.
- Each run snapshots provider, model, endpoint family, prompt template revision, run metadata, and context before execution.

### Flexible Prompt Composition

- Prompt templates support `single` and `two_step` modes.
- Global snippets are reusable prompt fragments inserted through placeholders.
- Placeholder resolution happens server-side against a frozen context snapshot before execution.

### Requests, Responses, And Versions

- Each run persists one request row per provider call.
- Each request stores rendered prompt text, placeholder map, and outbound payload snapshot without secrets.
- Each response stores raw provider payload, parsed payload, parse status, and usage when available.
- A version row is created only after the final structured response parses successfully.
- Versions remain immutable and queryable without reparsing historical raw payloads.

## Self-Reflection Operating Model

### Core Rule

Every review-bearing run must analyze the current stock from current evidence before it compares against prior versions. The workflow exists to reduce anchoring, narrative drift, and hindsight bias.

### Review Triggers

Supported review types map to common triggers:

- `initial_review`: first formal thesis for the symbol.
- `periodic_review`: scheduled or routine re-check.
- `event_review`: earnings, guidance change, management turnover, debt event, acquisition or divestiture, regulatory action, or a large price move.
- `manual_follow_up`: a user-driven follow-up question within the same conversation.

### Decision Boundary

The workflow should treat change as actionable only when at least one of these changes materially:

- intrinsic value;
- probability that the thesis is correct;
- downside risk;
- expected return;
- portfolio risk.

If none of those move materially, the correct result may still be `no_action`.

### Scorecard Guidance

The structured response may include a standardized scorecard across categories such as:

- business quality;
- management trust;
- competitive strength;
- growth durability;
- margin durability;
- balance-sheet strength;
- capital-allocation quality;
- valuation attractiveness;
- downside risk;
- overall conviction.

## Frontend Specification

### Tech Stack

React 19, Vite, TanStack Query 5, React Router 7, shadcn/Radix UI, Zod, Vitest, Playwright.

### Routes And Entry Points

- `/` — Dashboard with portfolio overview stats.
- `/portfolios` — Portfolio list with create/edit/delete.
- `/portfolios/:portfolioId` — Portfolio detail with summary metrics plus tabs for positions, balances, and trades.
- `/templates` — Global prompt template CRUD with single/two-step mode toggle.
- `/snippets` — Global user snippet CRUD.
- `/responses` — Stock analysis response viewer with portfolio and conversation filters.

### Key UI Components

- `Layout` / `Dashboard` — six-route app shell and overview landing page.
- `PortfolioListPage` / `PortfolioDetailPage` — portfolio CRUD and workspace.
- `PortfolioPositionsSection` — positions table with market data enrichment.
- `PortfolioBalancesSection` — balance CRUD.
- `PortfolioTradesSection` — trading operation history.
- `TradingOperationForm` — BUY/SELL/DIVIDEND/SPLIT discriminated union form.
- `PromptTemplates` — template management with mode toggle and placeholder guide.
- `Snippets` — snippet management.
- `ResponsesPage` — stored response browser with portfolio/conversation filters.
- `ErrorBoundary` — React error boundary with recovery UI.

### State Management

TanStack Query for all server state. No client-side store. Query key factory with portfolio-scoped invalidation via `invalidatePortfolioScope()`. Global resources (templates, snippets) use separate key namespaces.

### UX Behavior

- Destructive actions require confirmation.
- Trading-operation forms change fields based on the selected side.
- Market data renders warnings and stale state without blocking workspace access.
- Prompt preview renders via backend API, not client-side compilation.
- Stored stock-analysis responses remain browseable by portfolio and conversation.
- Loading skeletons shown during data fetches.
- Toast notifications for mutation success/error feedback.

## Backend Specification

### Router Modules

- `portfolios`
- `balances`
- `positions`
- `market_data`
- `trading_operations`
- `stock_analysis`
- `prompt_templates`

### Service Responsibilities

- `PortfolioService`: portfolio existence and shared portfolio lookup.
- `BalanceService`: balance CRUD and validation.
- `PositionService`: manual position CRUD.
- `CsvImportService`: preview and commit workflow.
- `TradingOperationService`: side-specific simulation rules and transactional updates.
- `MarketDataService`: delayed quote and history retrieval with warnings and cache-aware behavior.
- `StockAnalysisService`: settings, conversation, response-summary, and version orchestration.
- `AnalysisContextService`: context snapshot assembly, placeholder resolution, and prompt rendering.
- `PromptTemplateService`: template CRUD, archival, and preview helpers.
- `LlmGatewayService`: provider request assembly and dispatch.
- `StockAnalysisParserService`: strict structured-response validation.

## Stock-Analysis Preview And History Flow

### Phase 0. Preconditions

- The portfolio exists.
- The symbol is valid in portfolio context.
- A saved template or inline prompt text is available for preview when prompt rendering is requested.

### Phase 1. Conversation Selection Or Creation

- The user picks or creates a conversation for `(portfolio, symbol)`.
- The UI can then load stored responses or versions for that conversation.

### Phase 2. Context Snapshot Build

Before rendering a preview, the backend creates an immutable context snapshot that may include:

- portfolio metadata;
- position summary;
- delayed quote and price-history summary;
- preview metadata such as run type, trigger, and user note when supplied in the request.

### Phase 3. Prompt Preview

- Preview resolves placeholders without calling a provider.
- It returns rendered text, placeholder values, referenced records, warnings, and errors.
- Preview requests must fail fast when placeholder resolution or portfolio scoping is invalid.

### Phase 4. History Browsing

- The frontend reads stored response summaries and version rows for the selected portfolio or conversation.
- History rendering must not depend on provider retrieval APIs.

## Prompt System And Preview Behavior

### Provider-Neutral Rendering Model

Templates always render to two canonical strings:

- `instructions`
- `input`

Provider adapters then map those values into provider-specific payload shapes.

### Placeholder Grammar

```text
{{namespace.path}}
{{version:latest.path}}
{{version:origin.path}}
```

### Supported Namespaces

- Current snapshot: `portfolio.*`, `stock.*`, `position.*`, `quote.*`, `history.*`, `run.*`, `userNote.*`
- Current-run compare step only: `freshAnalysis.*`
- Version references: `version:latest.*`, `version:origin.*`

### Resolution Rules

- Resolution is single-pass only.
- No loops, conditionals, or code execution are allowed.
- All resolution happens on the backend.
- Version-reference loading fails validation when the selected conversation is outside the current portfolio or symbol.
- `freshAnalysis.*` is allowed only in the compare step and must resolve from the current run's parsed step-one payload.
- Missing current-context placeholders fail validation.
- Missing version references render an explicit unavailable sentinel such as `[version:latest.action not available]`.
- Scalars resolve to text; objects and arrays resolve to pretty JSON when no summary field exists.
- Null values fail validation by default.

### Preview-Execution Parity

- Preview and execution must use the same renderer and placeholder resolver.
- A prompt that previews successfully with the same snapshot inputs must render identically at execution time.
- Historical runs must never re-render from later template revisions.

### Snapshot Rules

- Every request stores rendered `instructions` and `input`.
- Every request stores a resolved placeholder map.
- Every request stores the provider-specific payload snapshot without secrets.
- `promptSource` records whether the prompt came from a saved template or an ad hoc draft.

## Provider-Specific Request Rules

### OpenAI Chat Completions

- Map rendered prompt text into `messages`.
- Attach structured-output controls through the chat endpoint's response-format settings.

### OpenAI Responses

- Map rendered prompt text into top-level `instructions` and `input`.
- Compare-step requests may include `previous_response_id` from the fresh-analysis response when available.

### Anthropic Messages

- Map rendered prompt text into top-level `system` plus `messages`.
- Enforce the same local JSON contract even when provider-side controls differ.

### Gemini Generate Content

- Map rendered prompt text into `contents` plus generation settings for structured JSON.

### Shared Rules

- Model ids are stored exactly as configured on the selected provider.
- Secrets and auth headers must never be persisted in request snapshots.
- Raw payloads and parsed payloads must both be stored when available.
- Provider request or response identifiers may be stored when returned.

## Structured Response Contract

### `freshAnalysis`

- `businessSummary`
- `currentContext`
- `thesis`
- `bearCase`
- `keyAssumptions[]`
- `valuation`
- `riskAssessment`
- `confidence`
- `scorecard`
- `provisionalAction`

### `comparison`

- `deltaVsLast`
- `deltaVsOrigin`
- `changeItems[]`
- `thesisChange`
- `fairValueChange`
- `riskChange`
- `confidenceChange`

Each `changeItem` must use one of:

- `new_fact`
- `changed_interpretation`
- `corrected_mistake`
- `noise`
- `thesis_strengthening`
- `thesis_weakening`
- `thesis_breaking`

### `decision`

- `action`
- `actionLevel`
- `reason`
- `reversalConditions[]`
- `shouldTradeNow`

Allowed actions:

- `buy`
- `add`
- `hold`
- `trim`
- `sell`
- `avoid`
- `watch`
- `no_action`

### `reflection`

- `whatGotRight`
- `whatWasMissed`
- `possibleBiases`
- `blankPageCheck`
- `nextReviewWatchpoints[]`

## Failure Handling

### Preview Failures

- Unknown namespace or path.
- Missing referenced record.
- Cross-portfolio or cross-symbol historical reference.
- Missing `freshAnalysis` payload for compare-step preview.
- No template text available.

Preview failures return validation errors and stop execution.

### Provider Failures

- Provider HTTP error.
- Timeout.
- Malformed payload.
- Missing required structured fields.

Provider failures must still persist truthful request and response metadata when available.

### Partial Success

If step one succeeds and step two fails:

- keep both request rows;
- keep the parsed step-one payload;
- mark the run `partial_failure`;
- do not materialize a new version.

### Parse Failure

- Persist raw provider payload.
- Mark parse status as `parsed_failure`.
- Keep the failed artifact visible in the timeline.

## Transaction Boundaries And Lifecycle Rules

- Trading-operation balance and position updates commit in one transaction.
- CSV import commit is atomic.
- Run creation persists the context snapshot before the first provider call.
- Each provider step persists its request row before the outbound call.
- Runs, requests, responses, and versions are immutable after creation except for in-flight status and parse metadata transitions.
- History viewers read from stored local snapshots rather than re-rendering from live provider state.
- Conversations archive instead of being deleted in the current release.
- Used templates archive instead of deleting.
- Referenced providers disable instead of deleting.

## Security And Advisory Boundary

- Outputs are decision support only.
- The analysis system never calls any trading-operation mutation path.
- Provider secrets stay server-side only.
- Cross-portfolio placeholder resolution is rejected even in the auth-less environment.
- Prompt transparency is required: the user can inspect the rendered prompt used for a request.

## Verification Strategy

### Backend Focus

- CRUD for portfolios, balances, positions, prompt templates, and stock-analysis settings.
- Trading-operation rules for `BUY`, `SELL`, `DIVIDEND`, and `SPLIT`.
- Prompt preview validation and placeholder-scope enforcement.
- Two-step run orchestration, parse validation, and version creation.

### Frontend Focus

- Run-form defaults and symbol switching.
- Prompt template management.
- Preview-before-submit behavior.
- Timeline rendering for success, partial failure, and parse failure.

### Integration Focus

- Preview-to-execution parity.
- Historical stability after template revision changes.
- Local rendering when provider retrieval is unavailable.
- Provider-path normalization across OpenAI, Anthropic, and Gemini.

### End-To-End Focus

- Initial review flow.
- Later periodic or event review with structured delta.
- Parse-failure visibility.
- Advisory-only boundary with no trade mutation from analysis.
