# Requirements Document

> Status: Live requirements reference for branch `main` at `e2c635f`.

## Purpose

Define the shipped SignalDeck requirements for a trusted single-user portfolio workspace and package-first agent platform. Live code is the source of truth; this document mirrors the browser and API surfaces mounted at the current branch tip.

## Product Scope

### In Scope

- Portfolio CRUD with balances, positions, CSV import, quote/history context, and trading operations.
- Template CRUD, placeholder browsing, inline compile, stored-template compile, and runtime inputs.
- Report generation from templates, external JSON report creation, markdown upload, slug CRUD, filtering, and download.
- Workflow Package authoring with `signaldeck.workflowPackage/v1` YAML validation, package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs in an authoring-only editor.
- Package import/export with no secrets, no encrypted credential payloads, no database ids, and no run history.
- Model Connection CRUD, encrypted stored secrets, OpenAI-family URL normalization, and connection testing as global live bindings.
- Global read-only Tools metadata from the server-declared catalog.
- Dedicated Workflow Package launch console at `/workflow-packages/:packageId/run` in phase 1, labeled `Launch Workflow Package`, with preflight gating and run creation outside the editor.
- Run list/detail, package provenance, rerun drafts, reruns, fork drafts, and invocation-input forks.

### Out Of Scope

- Public multi-user auth, live broker execution, realtime market streaming, and tax-lot accounting.
- Removed `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtest workflows, and global authoring routes.
- TradingAgents-specific platform behavior. TradingAgents is smoke/demo package data only.
- Raw HTTP LLM calls in application code when an official provider SDK exists.

## Functional Requirements

### FR-1 Portfolios, Balances, Positions, And Trades

- The system must isolate portfolio-owned balances, positions, trading operations, quote lookups, and analytics by `portfolioId`.
- Position CSV import must use preview and commit endpoints with row-level errors and atomic upsert-by-symbol commit.
- Trading operations must support BUY, SELL, DIVIDEND, and SPLIT with deterministic cash/position updates.
- Quote/history failures must degrade to warnings rather than making local portfolio records unusable.

### FR-2 Templates And Reports

- Templates must support `inputs`, `portfolios`, and `reports` placeholder roots.
- Dynamic portfolio and report selectors must accept runtime inputs where supported.
- Reports must support canonical `source` origins `compiled`, `uploaded`, `external`, and `agent`.
- `external` must remain limited to true external user/API-created reports; agent-created reports must use `source="agent"`.
- Report reads, updates, deletes, and downloads must be slug-addressed.

### FR-3 Package-First Agent Platform

- Workflow Packages must be YAML-manifest based and reject aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate local refs, raw model connection ids, and unsupported `spec.skills` fields.
- Package-private agents, output schemas, capability profiles, and workflow graphs must stay inside immutable package versions. Private MCP configs must stay inline as `env`, `headers`, and `query` manifest text.
- Package exports must keep private MCP `env`, `headers`, and `query` values inline and still omit database ids and run history.
- Model Connections must preserve or replace stored secrets safely, never return raw secrets in read payloads, and resolve by global key at preflight, launch, and runtime.
- Tools must be read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles for market data, indicators, fundamentals, news, insider data, positions, report lookup, and platform-core memory write/lookup.
- Package launches must use the strict launch envelope from the dedicated `/workflow-packages/:packageId/run` page and create queued global runs with immutable package provenance. The editor must remain authoring-only and must not own launch runtime state.
- Runs must expose input, per-step outputs, final output, status, timing, token usage, optional Logfire trace/span ids, package provenance, rerun lineage, invocation-input fork lineage, and historical replay lineage when an old run has it.
- Rerun must be the root-parameter descendant flow. Fork must be the invocation-input descendant flow, keyed by `sourceInvocationId`, persisted through `run_forks`, with `resumeStepIndex` used only as the execution boundary. `RunRead` does not expose a top-level `fork` metadata field today.

## Non-Functional Requirements

- Backend stack: Python 3.13+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL.
- Frontend stack: React 19, Vite, TanStack Query, React Router, shadcn/ui, Vitest, Playwright.
- Backend validation errors must use the shared error envelope.
- Logfire telemetry must remain optional: traces enrich persisted run metadata when configured, but provider or run execution cannot require a Logfire token.
- Application LLM calls must use official SDKs rather than raw provider HTTP paths.
- CI must run version sync, backend quality, frontend quality, and frontend E2E.

## Acceptance Criteria

- A user can manage portfolio records and reports without provider availability.
- A user can author Workflow Packages, configure Model Connections, view Tools, launch saved package runs from `/workflow-packages/:packageId/run`, and inspect Runs from the browser.
- Removed Studio, Tryout, orchestration, runtime-v2, simulation, backtest, `/api/skills`, `/skills*`, and global authoring routes are not presented as current product surfaces.
