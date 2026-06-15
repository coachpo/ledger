# Requirements Document

> Status: Live requirements reference for branch `main` at `6c40d44`.

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
- Model Connection CRUD, encrypted stored secrets, OpenAI-family `protocolProfile` selection, backend-owned compatibility evidence, reachability tests, capability probes, and secret-safe read payloads.
- Global read-only Tools metadata from the server-declared catalog, filtered by extension state where tools are extension-owned, including Digital Oracle-owned `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`.
- Dedicated Workflow Package launch console at `/workflow-packages/:packageId/run`, with preflight gating and run creation outside the editor.
- Scheduled Tasks for recurring Workflow Package runs, including structured recurrence, scheduled input previews, run-now, fire history while the schedule exists, and deletion that preserves existing run history while stopping future automation.
- Run list/detail, backend-owned progress/queue read models, package provenance, rerun drafts, reruns, fork drafts, invocation-input forks, operation invocation evidence, memory evidence, typed failure taxonomy, and bounded retry evidence.
- Platform-core memory surfaces: scoped runtime `/api/memory` workflows plus trusted local operator `/api/memory/admin/entries*` and `/memory` admin management over canonical workflow memory across packages.

### Out Of Scope

- Public multi-user auth, live broker execution, realtime market streaming, tax-lot accounting, and user-facing autonomous scheduling.
- Removed `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtest workflows, global Digital Oracle skill surfaces, and standalone global authoring routes.
- TradingAgents-specific platform behavior, exact LangGraph graph parity, checkpoint/runtime semantics, or agent-initiated trading execution.
- Unscoped runtime memory search, public memory CRUD, exact-id `signaldeck.core.memory.get`, vector activation/search, chunk or embedding retrieval contracts, runtime/global/public/bulk memory deletion, runtime tags, arbitrary core-memory attributes, core-memory audit links, and report-history promotion in phase 1. Trusted admin single-entry hard delete is part of the shipped Memory Admin management surface.
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
- Package-specific methodology, including Digital Oracle research policy, must live in package-local agent `systemPrompt` text and must not be modeled as `spec.skills`, `/api/skills`, or a global skill surface.
- Private MCP configs may use inline `env`, `headers`, and `query` manifest text for authoring/runtime, but those fields are secret-bearing request config.
- Package exports and browser-visible manifest reads must omit private MCP `env`, `headers`, and `query` values while also omitting database ids, run history, package secret binding rows, and raw package secret binding values.
- Package secret binding reads must expose only key, package id, presence, and timestamps; writes must store encrypted values; deletes must remove live bindings without rewriting package artifacts.
- Secret references must be valid only inside HTTP request fields: `url`, `headers`, `query`, and `body`.
- HTTP operation nodes must use `kind: http`, support only allowed methods, apply strict timeout/size/redirect/private-network defaults, redact secret-backed metadata, validate JSON/text responses against `response.outputSchema`, and persist operation invocation evidence separately from agent invocations.

### FR-4 Model Connections, Tools, And Extensions

- Model Connections must preserve or replace stored secrets safely, never return raw secrets in read payloads, and resolve by global key at preflight, launch, rerun, fork, and runtime.
- Model Connections must keep `protocolProfile` as the writable runtime selector and expose capability states, policy defaults, reachability-test metadata, capability-probe metadata, and derived API-style evidence as backend-owned read data.
- Public Model Connection create/update payloads must reject client-authored capabilities, runtime policy fields, probe cache TTL, derived API style, `compatibilityProfile`, and other compatibility truth that is not part of the write DTO.
- Tools must be read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles.
- Finance-owned tool entries must be hidden while `signaldeck.finance` is disabled; platform-core memory tools must remain visible.
- Digital Oracle-owned tool entries must be hidden while `signaldeck.digital_oracle` is disabled; platform-core memory tools must remain visible.
- The shipped Digital Oracle tools must be limited to `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`; their tool keys must remain canonical owner-qualified contracts and their OpenAI function names must remain mechanical forms derived from those keys. Speculative phase-2 tools and raw provider payloads must not be documented or exposed as shipped contracts.
- Retired report-write tool names, including `signaldeck_reports_write`, must fail closed at native dispatch and must not reappear through live tool discovery or MCP fallback.
- `/api/extensions` must expose only `key`, `label`, and `enabled`; toggle requests must accept only `enabled`.
- `signaldeck.finance` is a statically resident, default-enabled bundled extension.
- `signaldeck.digital_oracle` is a statically resident, default-enabled bundled extension. Digital Oracle has no route or nav surface in this upgrade.

### FR-5 Launches, Runs, Reruns, Forks, And Memory

- Package launches must use the strict launch envelope from `/workflow-packages/:packageId/run` and create durable queued global runs with immutable package provenance.
- Scheduled Tasks must target one current Workflow Package workflow, use structured recurrence with IANA timezones, and materialize due fires into queued runs with schedule provenance.
- Scheduled input previews must validate rendered parameters without creating fires or runs; run-now must create an idempotent manual fire and return the linked run summary.
- Deleting a Scheduled Task must remove the schedule and schedule-owned fire rows, stop future automation, preserve existing run history, and keep direct run artifacts readable through run-owned `scheduleProvenance`. Deleted schedule fire history must not be exposed as a preserved live surface.
- Workflow Package deletion semantics must remain unchanged: deleting a package still deletes its owned runs.
- Startup schema repair must detach legacy schedule rows from linked runs, backfill `scheduleProvenance` when resolvable, delete obsolete schedule and fire rows, and no longer route schedule cleanup through a destructive path.
- Launch, rerun, and fork requests must stop after creating queued rows; the explicit scheduler worker must claim and execute queued runs.
- Runs must expose input, per-step outputs, operation invocations, final output, status, backend-owned progress, queue reason, timing, token usage, optional trace/span ids, package provenance, extension dependencies, memory artifacts, memory events, typed failure taxonomy, bounded `toolCallRetries`, distinct live-execution `providerRetries` when emitted by the backend, rerun lineage, invocation-input fork lineage, and historical replay lineage when present.
- Runtime `toolCallRetries` must be admitted only from typed pre-dispatch JSON/object/schema/argument-validation failures, with one bounded model-feedback retry and redacted retry metadata. Provider/network/auth/permission/grant/namespace/extension-disabled/MCP transport/executor/policy/output-schema failures must remain fatal for the tool-call retry path.
- Live Workflow Package execution may record `graphMetadata.modelGateway.providerRetries` for transient provider create-call retries only. The contract must use `policy="transientProviderRetry/v1"`, `maxAttempts=3`, failed-attempt-only `attempts[]`, and `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. First-attempt success and first non-retryable failure must omit `providerRetries` entirely. Connection tests, capability probes, and Responses manual replay must stay outside provider retry metadata.
- Rerun must be the root-parameter descendant flow.
- Fork must be the invocation-input descendant flow, keyed by `sourceInvocationId`, persisted through `run_forks`, with `resumeStepIndex` used only as the execution boundary.
- Runtime memory writes must use `signaldeck.core.memory.write`; runtime memory lookup must use `signaldeck.core.memory.lookup`; exact-id `signaldeck.core.memory.get` remains out of scope.
- Runtime memory write and lookup contracts must stay lean, allowlisted, scoped, and free of arbitrary attributes, runtime tags, report identity, audit links, chunks, embeddings, and caller-authored namespace grants.
- Runtime memory lookup must never be unscoped global search; omitted runtime-tool selectors must fall back to the current run/package/agent context and runtime matching rules. Lookup selectors must not accept tags, attributes, report selectors, chunk selectors, embedding selectors, or vector-search controls.
- Runtime memory writes must create immutable revisions, reuse exact duplicate active revisions, and return retryable `memory_revision_conflict` for competing shared-scope mutations.
- Shared memory namespaces must be package-owned as `{ownerPackageKey}/{namespaceKey}` and require explicit read/write grants for non-owner access. Wildcards, ownerless namespaces, global search, and cross-package private writes must fail closed.
- `/api/memory` must remain a platform-core route family, not `/api/v1` finance routing. Its scoped list/detail/resolve/reflect paths must not provide admin-style all-package reads, runtime revisions, runtime events, or scoped history feeds.
- `/api/memory/admin/entries*` and `/memory` must provide trusted local operator/admin management over canonical workflow memory across packages, with optional filters that narrow rather than authorize the corpus.
- Runtime memory lookup must return only workflow-visible entries that match runtime scope and grant rules, and lookup output must omit `visibleToWorkflow`.
- Runtime memory writes must default hidden with `visibleToWorkflow=false`; write output must include `visibleToWorkflow`.
- Admin create, revise, and workflow-visibility operations must write canonical memory through explicit scope, `visible_to_workflow`, subject refs, operator provenance, immutable revision, and append-only typed event semantics using `memory_admin` channel metadata. Admin review/history data must be typed revision and event surfaces, not arbitrary entry or revision attributes.
- Admin create must default visible with `visibleToWorkflow=true`; admin list must default to all entries and support optional `visibleToWorkflow=true|false` filtering.
- Historical `approved`, `pending`, and `archived` values are migration-only inputs: startup repair maps `approved` to visible and `pending` or `archived` to hidden. They must not be live Memory Admin or runtime eligibility states.
- Model-visible memory outputs must not expose report identity, download URLs, raw markdown, audit links, arbitrary attributes, runtime tags, chunks, embeddings, or vector scores. API/UI memory projections must not include finance report-history rows. Run memory artifacts may retain their own non-runtime report or audit evidence as run evidence without making that evidence part of core runtime memory lookup.
- Startup repair coverage may prove obsolete chunk and embedding table removal, but chunk, embedding, and vector persistence must not be documented as live runtime, admin, or UI behavior.

## Non-Functional Requirements

- Backend stack: Python 3.13+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL.
- Frontend stack: React 19, Vite, TanStack Query, React Router, shadcn/ui, Vitest, Playwright.
- Backend validation errors must use the shared error envelope.
- Logfire telemetry must remain optional: traces enrich persisted run metadata when configured, but provider or run execution cannot require a Logfire token.
- Application LLM calls must use official SDKs rather than raw provider HTTP paths.
- CI must run version sync, backend quality, frontend quality, and frontend E2E.
- Finance-owned behavior must remain extension-owned unless explicitly promoted to platform core.
- Platform-core memory tools, `/api/memory`, and `/memory` must operate separately from Finance Workspace report history, extension-owned report lookup, and finance follow-up metadata stored outside canonical core memory rows.

## Acceptance Criteria

- A user can manage portfolio records, templates, and reports without provider availability.
- A local operator can author Workflow Packages, configure Model Connections, select server-declared Tools metadata during package authoring, launch saved package runs from `/workflow-packages/:packageId/run`, schedule recurring package runs, hard-delete Scheduled Tasks, inspect Runs, and manage canonical Memory from the trusted `/memory` admin route.
- The Digital Oracle researcher demo path is `demo/digital_oracle_researcher.yaml`; it must grant the three phase-1 `signaldeck.digital_oracle` tools through package-local capability profiles and keep methodology in `systemPrompt`, not a global skill.
- Package HTTP operations can be authored, bound to package-local secrets, launched, and inspected without exposing raw secret values.
- Run detail exposes backend-owned progress, queue state, agent invocations, operation invocations, package provenance, extension dependencies, memory artifacts, memory events, typed failure taxonomy, and bounded retry evidence.
- Runtime `/api/memory` and `signaldeck.core.memory.lookup/write` stay scoped and do not act as global memory search; `/memory` uses trusted operator admin visibility over canonical memory and does not surface finance report history, arbitrary attributes, runtime tags, chunks, embeddings, or core-memory audit links as platform memory.
- Removed Studio, Tryout, orchestration, runtime-v2, simulation, backtest, `/api/skills`, `/skills*`, global Digital Oracle skill surfaces, and standalone global authoring routes are not presented as current product surfaces.
