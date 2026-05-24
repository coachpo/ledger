# Requirements Document

> Status: Live requirements reference for branch `main` at `adc9887`.

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
- Model Connection CRUD, encrypted stored secrets, OpenAI-family protocol profiles, reachability tests, capability probes, and secret-safe read payloads.
- Global read-only Tools metadata from the server-declared catalog, filtered by extension state where tools are extension-owned.
- Dedicated Workflow Package launch console at `/workflow-packages/:packageId/run`, with preflight gating and run creation outside the editor.
- Run list/detail, backend-owned progress/queue read models, package provenance, rerun drafts, reruns, fork drafts, invocation-input forks, operation invocation evidence, and memory evidence.

### Out Of Scope

- Public multi-user auth, live broker execution, realtime market streaming, tax-lot accounting, and user-facing autonomous scheduling.
- Removed `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtest workflows, and standalone global authoring routes.
- TradingAgents-specific platform behavior, exact LangGraph graph parity, checkpoint/runtime semantics, or agent-initiated trading execution.
- Public browser memory CRUD, exact-id `signaldeck.memory.get`, vector search, embeddings, and chunk tables in phase 1.
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

- Workflow Packages must be YAML-manifest based and reject aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate local refs, raw model connection ids, and unsupported `spec.skills` fields.
- Package-private agents, output schemas, capability profiles, private MCP configs, HTTP operation nodes, and workflow graphs must stay inside package artifacts.
- Private MCP configs must stay inline as `env`, `headers`, and `query` manifest text.
- Package exports must keep private MCP `env`, `headers`, and `query` values inline while omitting database ids, run history, package secret binding rows, and raw package secret binding values.
- Package secret binding reads must expose only key, package id, presence, and timestamps; writes must store encrypted values; deletes must remove live bindings without rewriting package artifacts.
- Secret references must be valid only inside HTTP request fields: `url`, `headers`, `query`, and `body`.
- HTTP operation nodes must use `kind: http`, support only allowed methods, apply strict timeout/size/redirect/private-network defaults, redact secret-backed metadata, validate JSON/text responses against `response.outputSchema`, and persist operation invocation evidence separately from agent invocations.

### FR-4 Model Connections, Tools, And Extensions

- Model Connections must preserve or replace stored secrets safely, never return raw secrets in read payloads, and resolve by global key at preflight, launch, rerun, fork, and runtime.
- Model Connections must expose `protocolProfile`, capability states, policy defaults, reachability-test metadata, and capability-probe metadata separately.
- Tools must be read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles.
- Finance-owned tool entries must be hidden while `signaldeck.finance` is disabled, while platform-core memory tools must remain visible.
- `/api/extensions` must expose only `key`, `label`, and `enabled`; toggle requests must accept only `enabled`.

### FR-5 Launches, Runs, Reruns, Forks, And Memory

- Package launches must use the strict launch envelope from `/workflow-packages/:packageId/run` and create durable queued global runs with immutable package provenance.
- Launch, rerun, and fork requests must stop after creating queued rows; the explicit scheduler worker must claim and execute queued runs.
- Runs must expose input, per-step outputs, operation invocations, final output, status, backend-owned progress, queue reason, timing, token usage, optional trace/span ids, package provenance, extension dependencies, memory artifacts, memory events, rerun lineage, invocation-input fork lineage, and historical replay lineage when present.
- Rerun must be the root-parameter descendant flow.
- Fork must be the invocation-input descendant flow, keyed by `sourceInvocationId`, persisted through `run_forks`, with `resumeStepIndex` used only as the execution boundary.
- Core memory writes must use `signaldeck.memory.write`; core memory lookup must use `signaldeck.memory.lookup`; exact-id `signaldeck.memory.get` remains out of scope.
- Memory lookup must never be unscoped global search; omitted selectors must fall back to the current run/package/agent context.
- Memory writes must create immutable revisions, reuse exact duplicate active revisions, and return retryable `memory_revision_conflict` for competing shared-scope mutations.
- Model-visible memory outputs must not expose report identity, download URLs, raw markdown, or audit links.

## Non-Functional Requirements

- Backend stack: Python 3.13+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL.
- Frontend stack: React 19, Vite, TanStack Query, React Router, shadcn/ui, Vitest, Playwright.
- Backend validation errors must use the shared error envelope.
- Logfire telemetry must remain optional: traces enrich persisted run metadata when configured, but provider or run execution cannot require a Logfire token.
- Application LLM calls must use official SDKs rather than raw provider HTTP paths.
- CI must run version sync, backend quality, frontend quality, and frontend E2E.
- Finance-owned behavior must remain extension-owned unless explicitly promoted to platform core.
- Platform-core memory must operate with the Finance Workspace disabled.

## Acceptance Criteria

- A user can manage portfolio records, templates, and reports without provider availability.
- A user can author Workflow Packages, configure Model Connections, view Tools, launch saved package runs from `/workflow-packages/:packageId/run`, and inspect Runs from the browser.
- Package HTTP operations can be authored, bound to package-local secrets, launched, and inspected without exposing raw secret values.
- Run detail exposes backend-owned progress, queue state, agent invocations, operation invocations, package provenance, extension dependencies, memory artifacts, and memory events.
- Removed Studio, Tryout, orchestration, runtime-v2, simulation, backtest, `/api/skills`, `/skills*`, and standalone global authoring routes are not presented as current product surfaces.
