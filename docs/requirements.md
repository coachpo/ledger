# Requirements Document

> Status: Live requirements reference for the current branch.

## Purpose

Define the shipped SignalDeck requirements for a trusted single-user finance workspace and package-first agent platform. Live code is the source of truth; this document is the normative requirement owner for mounted browser/API surfaces, validation behavior, and acceptance criteria.

## Product Scope

### In Scope

- Portfolio CRUD with balances, positions, CSV import, quote/history context, and trading operations under the `signaldeck.finance` extension.
- Template CRUD, placeholder browsing, inline compile, stored-template compile, and runtime inputs.
- Report generation from templates, external JSON report creation, markdown upload, slug CRUD, filtering, and download.
- Workflow Package authoring with `signaldeck.workflowPackage/v1` YAML validation, package-private agents, output schemas, capability profiles, private MCP configs, HTTP operations, and workflow graphs in an authoring-only editor.
- Package secret bindings for package-local encrypted HTTP operation secrets.
- Package import/export with no database ids, no run history, no package secret binding rows, and no raw secret values.
- Model Connection CRUD, encrypted stored secrets, OpenAI-family `protocolProfile` selection, backend-owned capability evidence, reachability tests, capability probes, and secret-safe read payloads.
- Global read-only Tools metadata from the server-declared catalog, filtered by extension state where tools are extension-owned, including Digital Oracle-owned `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`.
- Dedicated Workflow Package launch console at `/workflow-packages/:packageId/run`, with preflight gating and run creation outside the editor.
- Scheduled Tasks for recurring Workflow Package runs, including structured recurrence, scheduled input previews, run-now, fire history while the schedule exists, and deletion that preserves existing run history while stopping future automation.
- Run list/detail, backend-owned progress/queue read models, package provenance, rerun drafts, reruns, operation invocation evidence, typed failure taxonomy, and bounded retry evidence.

### Out Of Scope

- Public multi-user auth, live broker execution, realtime market streaming, tax-lot accounting, and user-facing autonomous scheduling.
- Removed `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtest workflows, global Digital Oracle skill surfaces, and standalone global authoring routes.
- Invocation-input run descendant APIs and UI.
- TradingAgents-specific platform behavior, exact LangGraph graph parity, checkpoint/runtime semantics, or agent-initiated trading execution.
- Workflow-memory governance, `spec.memory`, `/api/memory`, runtime memory tool calls, unscoped runtime memory search, public memory CRUD, exact-id runtime memory get, checkpoints, `workflowMemoryEvidence`, vector activation/search, chunk or embedding retrieval contracts, runtime/global/public/bulk memory deletion, runtime tags, arbitrary core-memory attributes, core-memory audit links, and report-history promotion.
- Raw HTTP LLM calls in application code when an official provider SDK exists.

## Functional Requirements

### FR-1 Portfolios, Balances, Positions, And Trades

- The system must isolate portfolio-owned balances, positions, trading operations, quote lookups, and analytics by `portfolioId`.
- Position CSV import must use preview and commit endpoints with row-level errors and atomic upsert-by-symbol commit.
- Trading operations must support BUY, SELL, DIVIDEND, and SPLIT with deterministic cash/position updates.
- Quote/history failures must degrade to warnings rather than making local portfolio records unusable.

### FR-2 Templates, Runtime Inputs, And Reports

- Templates must support the `inputs`, `portfolios`, and `reports` placeholder roots.
- Dynamic portfolio and report selectors must accept runtime inputs where supported.
- Workflow package run input schemas may use JSON Schema `title` and `description` as display metadata only.
- Runtime input `title` and `description` must not change runtime JSON, value-entry encoding, validation semantics, workflow wiring, or agent invocation semantics.
- YAML comments, `comment` fields, `x-signaldeck-*` metadata, `patternProperties`, `oneOf`, `allOf`, `if`, `then`, `else`, `not`, and schema-valued `additionalProperties` must not be treated as supported help-text mechanisms.
- Reports must support canonical `source` origins `compiled`, `uploaded`, `external`, and `agent`.
- `external` must remain limited to true external user/API-created reports; agent-created reports must use `source="agent"`.
- Report reads, updates, deletes, and downloads must be slug-addressed.

### FR-3 Workflow Packages And Package Secrets

- Workflow Packages must be YAML-manifest based and reject aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate local refs, raw model connection ids, and unsupported `spec.skills` and `spec.memory` fields.
- Package-private agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and workflow graphs must stay inside package artifacts.
- Package-specific methodology, including Digital Oracle research policy, must live in package-local agent `systemPrompt` text and must not be modeled as `spec.skills`, `/api/skills`, or a global skill surface.
- Private MCP configs may use inline `env`, `headers`, and `query` manifest text for authoring/runtime, but those fields are secret-bearing request config.
- Package exports and browser-visible manifest reads must omit private MCP `env`, `headers`, and `query` values while also omitting database ids, run history, package secret binding rows, and raw package secret binding values.
- Package secret binding reads must expose only key, package id, presence, and timestamps; writes must store encrypted values; deletes must remove live bindings without rewriting package artifacts.
- Secret references must be valid only inside HTTP request fields: `url`, `headers`, `query`, and `body`.
- HTTP operation nodes must use `kind: http`, support only allowed methods, apply strict timeout/size/redirect/private-network defaults, redact secret-backed metadata, validate JSON/text responses against `response.outputSchema`, and persist operation invocation evidence separately from agent invocations.

### FR-4 Model Connections, Tools, And Extensions

- Model Connections must preserve or replace stored secrets safely, never return raw secrets in read payloads, and resolve by global key at preflight, launch, rerun, and runtime.
- Model Connections must keep `protocolProfile` as the writable runtime selector and expose capability states, policy defaults, reachability-test metadata, capability-probe metadata, and derived API-style evidence as backend-owned read data.
- Public Model Connection create/update payloads must reject client-authored capabilities, runtime policy fields, probe cache TTL, derived API style, and other capability/runtime-profile truth that is not part of the write DTO.
- Tools must be read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles.
- Finance-owned tool entries must be hidden while `signaldeck.finance` is disabled.
- Workflow Package demos must use canonical owner-qualified `toolKeys`: the TradingAgents advisory demo must stay Finance-only on `signaldeck.finance.*` keys, the Digital Oracle Researcher demo must stay Digital-Oracle-only on `signaldeck.digital_oracle.*` keys, and any mixed-extension research behavior must be explicit package-level composition rather than a bundled demo contract. Mixed TradingAgents research may combine Finance tools with `signaldeck.digital_oracle.macro_rates.lookup` and `signaldeck.digital_oracle.prediction_markets.lookup` by default; prompts must explicitly grant and use any broader Digital Oracle tools.
- `signaldeck.finance.indicators.lookup` must remain the single Finance-owned indicators key and must accept an `indicators[]` selection shape for SMA, EMA, RSI, MACD, Bollinger bands, ATR, and VWMA. Results must preserve `rows[].values[]`, deterministic indicator value names, camelCase fields, and `nullReason` values for warmup, insufficient history, or provider gaps without exposing raw provider payloads.
- `signaldeck.finance.fundamentals.lookup` must remain the single Finance-owned fundamentals key and must keep `signaldeck_finance_fundamentals_lookup` as the OpenAI function name. It must support bounded `metricNames`, `statementTypes`, `periods`, and `statementLimit` filters while preserving `metrics[]`, `statements[]`, `warnings[]`, camelCase serialization, provider-unavailable warnings, and no raw provider payloads or private provider configuration leakage.
- `signaldeck.finance.news.lookup` must remain the only Finance-owned news key and must keep `signaldeck_finance_news_lookup` as the OpenAI function name. It must support existing `symbols`, `query`, `startDate`, `endDate`, and `itemLimit` fields plus bounded `scope` values of `symbol`, `market`, and `global`, while preserving `items[]`, `symbols`, `query`, bounded dates, `warnings[]`, camelCase serialization, provider-empty/truncated/global-coverage warnings, and no raw provider payloads or combined social-sentiment mutation. Runtime dispatch must resolve Alpha Vantage credentials only from package/caller runtime secret `alpha_vantage_api_key`, use Yahoo news providers without credential env state, and report provider warnings without exposing request URLs, API keys, Authorization headers, or raw payloads.
- `signaldeck.finance.social_sentiment.lookup` must stay separate from `signaldeck.finance.news.lookup`. Reddit and StockTwits provider degradation must return structured warnings and empty/partial normalized source blocks where applicable, with Reddit RSS/JSON and StockTwits behavior covered by fake-provider tests rather than live-network checks.
- Digital Oracle-owned tool entries must be hidden while `signaldeck.digital_oracle` is disabled.
- The shipped Digital Oracle tools are `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`; their tool keys remain canonical owner-qualified contracts and their OpenAI function names are mechanical forms derived from those keys.
- `signaldeck.digital_oracle.prediction_markets.lookup` must preserve its existing event/contract lookup response while accepting optional `includeOrderBook` and bounded `depthLimit` controls. When requested and available, normalized contract-level `orderBook` fields must serialize as camelCase `bids[]`, `asks[]`, `spread`, and `depthLimit`; unavailable, malformed, or partial venue depth must be reported through stable `warnings[]` without exposing raw provider payloads.
- `signaldeck.digital_oracle.sec_filings.lookup` must preserve existing `ticker`, `formTypes`, `startDate`, `endDate`, and `itemLimit` behavior while accepting optional `query`, optional `cik`, and optional `includeOwnershipTransactions`. Results must expose normalized filing summaries plus camelCase `searchHits[]` and `ownershipTransactions[]` when requested or available, must report empty/partial/stale/provider-limited EDGAR coverage through stable `warnings[]`, and must not expose raw SEC archive contents, raw provider payloads, or backend EDGAR contact-email configuration.
- `signaldeck.digital_oracle.macro_rates.lookup` must expose normalized macro/rate series and observations through strict request parsers, camelCase result payloads, structured warnings for missing provider coverage or missing optional FRED runtime secret `fred_api_key`, and no raw provider payloads.
- `signaldeck.digital_oracle.crypto_derivatives.lookup` must expose normalized crypto derivatives market data through strict request parsers, camelCase result payloads, structured warnings for empty, stale, truncated, or provider-limited coverage, and no raw provider payloads.
- `signaldeck.digital_oracle.cftc_positioning.lookup` must expose normalized CFTC positioning summaries through strict request parsers, camelCase result payloads, structured warnings for unavailable reports, stale releases, empty coverage, or provider limits, and no raw provider payloads.
- `signaldeck.digital_oracle.options.lookup` must expose normalized options-chain data through strict request parsers, camelCase result payloads, structured warnings for unavailable symbols, provider gaps, or missing optional `yfinance` dependency, and no raw provider payloads.
- Unsupported native tool names must fail closed at dispatch and must not fall through to MCP fallback.
- `/api/extensions` must expose only `key`, `label`, and `enabled`; toggle requests must accept only `enabled`.
- `signaldeck.finance` is a statically resident, default-enabled bundled extension.
- `signaldeck.digital_oracle` is a statically resident, default-enabled bundled extension. Digital Oracle has no route or nav surface in this upgrade, and the provider migration adds no new provider-settings UI route.

### FR-5 Launches, Runs, And Reruns

- Package launches must use the strict launch envelope from `/workflow-packages/:packageId/run` and create durable queued global runs with immutable package provenance.
- Scheduled Tasks must target one current Workflow Package workflow, use structured recurrence with IANA timezones, and materialize due fires into queued runs with schedule provenance.
- Scheduled input previews must validate rendered parameters without creating fires or runs; run-now must create an idempotent manual fire and return the linked run summary.
- Deleting a Scheduled Task must remove the schedule and schedule-owned fire rows, stop future automation, preserve existing run history, and keep direct run artifacts readable through run-owned `scheduleProvenance`. Deleted schedule fire history must not be exposed as a preserved live surface.
- Workflow Package deletion semantics must remain unchanged: deleting a package still deletes its owned runs.
- Launch and rerun requests must stop after creating queued rows; the explicit scheduler worker must claim and execute queued runs.
- Runs must expose input, per-step outputs, operation invocations, final output, status, backend-owned progress, queue reason, timing, token usage, optional trace/span ids, package provenance, extension dependencies, typed failure taxonomy, bounded `toolCallRetries`, distinct live-execution `providerRetries` when emitted by the backend, and rerun lineage.
- Runtime `toolCallRetries` must be admitted only from typed pre-dispatch JSON/object/schema/argument-validation failures, with one bounded model-feedback retry and redacted retry metadata. Provider/network/auth/permission/grant/namespace/extension-disabled/MCP transport/executor/policy/output-schema failures must remain fatal for the tool-call retry path.
- Live Workflow Package execution may record `graphMetadata.modelGateway.providerRetries` for transient provider create-call retries only. The contract must use `policy="transientProviderRetry/v1"`, `maxAttempts=3`, failed-attempt-only `attempts[]`, and `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. First-attempt success and first non-retryable failure must omit `providerRetries` entirely. Connection tests, capability probes, and Responses manual replay must stay outside provider retry metadata.
- Rerun must be the root-parameter descendant flow.

## Non-Functional Requirements

- Backend stack: Python 3.13+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL.
- Frontend stack: React 19, Vite, TanStack Query, React Router, shadcn/ui, Vitest, Playwright.
- Backend validation errors must use the shared error envelope.
- Logfire telemetry must remain optional: traces enrich persisted run metadata when configured, but provider or run execution cannot require a Logfire token.
- Application LLM calls must use official SDKs rather than raw provider HTTP paths.
- CI must run version sync, backend quality, frontend quality, and frontend E2E.
- Finance-owned behavior must remain extension-owned unless explicitly promoted to platform core.
- Finance Workspace report history, extension-owned report lookup, and finance follow-up metadata must remain report-domain behavior rather than workflow-memory records.

## Acceptance Criteria

- A user can manage portfolio records, templates, and reports without provider availability.
- A local operator can author Workflow Packages, configure Model Connections, select server-declared Tools metadata during package authoring, launch saved package runs from `/workflow-packages/:packageId/run`, schedule recurring package runs, hard-delete Scheduled Tasks, and inspect Runs.
- The Digital Oracle researcher demo path is `demo/digital_oracle_researcher.yaml`; it must grant the seven shipped `signaldeck.digital_oracle` tools through package-local capability profiles and keep methodology in `systemPrompt`, not a global skill.
- The TradingAgents advisory demo path is `demo/tradingagents_advisory_research.yaml`; it must grant only Finance-owned tools and must not add Digital Oracle, Finance-owned prediction-market, or ownerless prediction-market aliases.
- Package HTTP operations can be authored, bound to package-local secrets, launched, and inspected without exposing raw secret values.
- Run detail exposes backend-owned progress, queue state, agent invocations, operation invocations, package provenance, extension dependencies, typed failure taxonomy, and bounded retry evidence.
- Removed Studio, Tryout, orchestration, runtime-v2, simulation, backtest, workflow-memory governance, `spec.memory`, `/api/memory`, `workflowMemoryEvidence`, `/api/skills`, `/skills*`, global Digital Oracle skill surfaces, and standalone global authoring routes are not presented as current product surfaces.
