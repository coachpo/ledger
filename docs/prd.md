# Product Requirements Document (PRD)

## Product Summary

Ledger is a trusted single-user portfolio workspace for tracking balances, positions, delayed market context, simulated trading operations, and structured stock-analysis reviews. The product combines manual record keeping with LLM-assisted decision support so the user can preserve portfolio state and investment reasoning in one place without automating trade execution.

## Problem Statement

Users often split portfolio management across spreadsheets, notes, broker dashboards, and ad hoc AI chats. That creates three persistent problems:

- portfolio state is easy to corrupt because balances, positions, and simulated trades are updated in different places;
- delayed market context is available, but the user still has to manually reconstruct what changed and why;
- investment reasoning is not versioned, so it is hard to tell whether a view changed because of new facts, narrative drift, market noise, or hindsight.

Ledger solves this by treating portfolio records and stock-analysis history as first-class product data. The product keeps manual portfolio state editable, stores every analysis artifact locally, and turns the self-reflection loop into a repeatable workflow: fresh analysis first, comparison second, then action and reflection.

## Target User

- A single operator or trusted internal user working in an auth-less environment.
- A user who wants explicit, editable portfolio records instead of broker connectivity or reconciliation-heavy tooling.
- A user who wants AI-assisted stock reviews with prompt transparency, version history, and decision support, not autonomous trading.

## Goals

- Keep each portfolio isolated so experiments in one workspace do not affect another.
- Make balances, positions, CSV imports, and simulated operations easy to understand and correct.
- Show delayed market data and history as helpful context without making core records depend on provider uptime.
- Support structured stock-analysis reviews that preserve fresh analysis, comparison, decision, and reflection over time.
- Let the user manage LLM configs and prompt templates from the UI while keeping secrets server-side.
- Preserve local history as the authoritative record for analysis timelines, replay, and audits.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, or automatic trade execution.
- Realtime quotes, websocket streaming, or autonomous alerting.
- External news, filings, or research ingestion in the current release.
- Provider-side threads or conversations as the product source of truth.
- Tax-lot accounting, FIFO, realized tax reporting, or accounting exports.

## Product Areas

### 1. Portfolio Workspace

- Portfolio list with create, edit, delete, and open flows.
- Portfolio detail workspace that keeps balances, positions, operations, market context, and stock analysis tied to one portfolio.
- Clear portfolio isolation in both API scope and UI navigation.

### 2. Balance And Position Management

- Manual CRUD for balances in the portfolio base currency.
- Manual CRUD for aggregate positions keyed by symbol.
- CSV position import with preview-before-commit and row-level validation.

### 3. Market Context

- Delayed quote retrieval for symbols in the active portfolio.
- Price-history retrieval for charting and analysis context.
- Freshness and warning metadata so the user can distinguish delayed data from authoritative portfolio records.

### 4. Simulated Operation Ledger

- Append-only simulated operations for `BUY`, `SELL`, `DIVIDEND`, and `SPLIT`.
- Deterministic balance and aggregate-position updates.
- Immediate feedback when an operation would violate business rules.

### 5. Stock Analysis Workspace

- Portfolio-scoped stock-analysis settings with enable/disable and defaults.
- Conversation timeline per `(portfolio, symbol)`.
- Review run creation for `initial_review`, `periodic_review`, `event_review`, and `manual_follow_up`.
- Structured viewer for fresh analysis, comparison, action memo, reversal conditions, and reflection.

### 6. LLM Config Manager

- CRUD for reusable provider configs.
- First-class support for OpenAI, Anthropic, and Gemini providers.
- OpenAI endpoint-mode selection for `chat_completions` or `responses`.
- Server-side secret storage with masked read behavior.

### 7. Prompt Template Manager

- CRUD and archival for reusable prompt templates.
- Separate prompt text for `fresh_analysis` and `compare_decide_reflect` steps.
- Preview rendering against live portfolio context before execution.
- Stable request snapshots so later template edits do not rewrite history.

## Core User Stories

- As a user, I want separate portfolios for different strategies so their balances, positions, operations, and analysis history stay isolated.
- As a user, I want to maintain balances and positions manually or by CSV so I can correct state quickly.
- As a user, I want simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations so Ledger can model portfolio changes without touching a broker.
- As a user, I want delayed quotes and price history for my symbols so I have context for simulation and review.
- As a user, I want to configure provider credentials and prompt templates in the product so I do not have to edit code to run reviews.
- As a user, I want each stock review to analyze the current situation first and compare against prior versions only afterward so I avoid anchoring to old conclusions.
- As a user, I want every run, prompt, response, and version snapshot stored locally so I can inspect what the model saw and why it recommended an action.
- As a user, I want the final result to include an explicit action stance, reversal conditions, and reflection notes so the output is operational rather than vague.

## Experience Principles

- Analyze first, compare later.
- Keep local history authoritative.
- Make non-action explicit.
- Prefer structured outputs over opaque chat transcripts.
- Show the rendered prompt and referenced context when possible.
- Keep AI advisory only; trades remain manual user actions.

## Key Screens

### Portfolio List

- Shows all portfolios and top-level portfolio actions.

### Portfolio Detail Workspace

- Header with portfolio metadata and currency.
- Balances, positions, operations, market context, and stock-analysis entry points.

### CSV Import Dialog

- File picker, validation preview, accepted rows, errors, and commit action.

### Stock Analysis Workspace

- Symbol selector, settings panel, run form, preview flow, and conversation timeline.

### LLM Config Manager

- Provider, model, endpoint mode, enabled state, base URL, and masked secret state.

### Prompt Template Manager

- Template list, revision-aware editing, archive flow, and preview support.

### Structured Review Viewer

- Panels for fresh analysis, comparison, action memo, reversal conditions, and reflection.

## Success Criteria

- A new portfolio can be created and populated with balances and positions in minutes.
- CSV validation is clear enough that the user can fix bad files without backend help.
- Simulated operations update balance and aggregate position state in one step and reject invalid requests deterministically.
- Delayed market quotes and price history remain visibly non-authoritative and do not block core record access.
- A user can configure an LLM config and template, preview a prompt, and submit a stock review without editing code.
- A user can run an initial review and later a periodic or event review for the same symbol and see a structured delta with preserved history.
- Historical analysis runs remain readable after later template edits, provider changes, or remote-provider retention expiry.

## Risks And Mitigations

- Public market data can be stale or unavailable; mitigate with warnings, freshness metadata, and non-blocking read behavior.
- Prompt brittleness can create unstable results; mitigate with preview, versioned templates, and stored snapshots.
- Provider contract differences can drift; mitigate with a shared normalized response model and strict parser validation.
- An auth-less deployment is unsafe for public exposure; mitigate by documenting trusted-environment usage clearly.
- Users may over-trust AI output; mitigate with advisory-only boundaries, explicit reversal conditions, and prompt transparency.
- Historical reasoning can become anchored to prior theses; mitigate with a mandatory fresh-analysis-first workflow.

## Release-Ready Definition

- Portfolio, balance, and position management work for isolated portfolios.
- CSV import validates and commits correctly.
- Delayed quotes and price history are available with warnings and freshness metadata.
- Simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` operations update state correctly.
- Stock analysis can be enabled per portfolio and executed with configurable LLM configs and prompt templates.
- Analysis runs persist conversations, requests, responses, and version snapshots locally.
- Final analysis outputs are structured, inspectable, and advisory only.
