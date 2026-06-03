# Technical Specification

> Status: Live technical reference for branch `main` at `1e43bf7`.

## Overview

SignalDeck is a dual-stack FastAPI and React/Vite application with preserved finance workflows and a package-first agent platform. Backend JSON is camelCase externally and snake_case internally. Preserved finance routes live under `/api/v1` through the bundled `signaldeck.finance` extension; platform routes live under `/api`.

The canonical execution model is immutable Workflow Package artifact plus late-bound execution environment. A run freezes the selected package artifact and non-secret runtime profile evidence, while live credentials, extension state, package secret bindings, provider behavior, and runtime infrastructure remain late-bound for readiness and execution.

## Runtime Topology

- Root startup is managed by `start.sh` with PostgreSQL `25432`, backend `28000`, frontend `25173`, and the scheduler worker as a sibling backend process; fallback ports are `25433/25434`, `28001/28002`, and `25174`.
- Manual backend startup expects PostgreSQL from `backend/docker-compose.yml` plus a separate `uv run python -m app.workers.run_scheduler` process when queued Workflow Package runs should execute.
- Playwright starts dedicated E2E servers on backend `8001` and frontend `4173`; the backend helper also launches the scheduler worker.
- Backend requires Python 3.13+, frontend targets Node 24 and pnpm 10.

## API Conventions

- Health path: `/health`.
- Preserved product base path: `/api/v1`, contributed by the bundled `signaldeck.finance` extension.
- Current agent-platform base path: `/api`.
- Standard format: JSON, except CSV and markdown uploads use `multipart/form-data`.
- External field names are camelCase.
- Decimal money, quantity, and market-value fields serialize as strings.
- Timestamps serialize as UTC ISO 8601 strings.
- Error envelopes use `{code, message, details[]}`.

## Backend Architecture

- `backend/app/main.py` owns app creation, exception handlers, CORS, and health.
- `backend/app/api/router.py` composes preserved `/api/v1` finance routes behind extension gates.
- `backend/app/api/platform_router.py` mounts `/api/memory`, `/api/workflow-packages`, `/api/schedules`, `/api/model-connections`, `/api/extensions`, `/api/tools`, and `/api/runs`.
- `backend/app/extensions/signaldeck_finance/` contributes current finance/product/provider routes, tools, hooks, and registrars as `signaldeck.finance`.
- `backend/app/api/dependencies.py` is the service composition root.
- `backend/app/core/telemetry.py` owns optional Logfire setup and trace/span id formatting.
- `backend/app/db/` owns PostgreSQL session lifecycle and startup schema repair.

## Frontend Architecture

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- `frontend/src/routes.ts` defines flat routes for dashboard, portfolios, templates, reports, Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Runs, and Memory. Tools are linked through package authoring metadata, not a standalone route.
- `frontend/src/components/layout.tsx` owns sidebar labels, breadcrumbs, and the app shell.
- `frontend/src/extensions/runtime-helpers.ts` assembles finance routes/nav from extension state; `ExtensionRead` is the slim `{key,label,enabled}` contract.
- API helpers live under `frontend/src/lib/api/`; wire types live under `frontend/src/lib/types/`; query keys live in `frontend/src/lib/query-keys.ts`.
- Platform authoring helpers under `frontend/src/lib/platform-authoring/` keep schema/value/ref/manifest transforms out of routed pages.

## Preserved Finance Product API

`signaldeck.finance` is enabled by default and gates preserved product APIs. Extension state supports enable and disable only.

| Resource           | Routes                                                                                                                                                                                                     |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Portfolios         | `GET/POST /api/v1/portfolios`, `GET/PATCH/DELETE /api/v1/portfolios/{portfolioId}`                                                                                                                         |
| Balances           | `GET/POST /api/v1/portfolios/{portfolioId}/balances`, `PATCH/DELETE /api/v1/portfolios/{portfolioId}/balances/{balanceId}`                                                                                 |
| Positions          | `GET/POST /api/v1/portfolios/{portfolioId}/positions`, `GET /api/v1/portfolios/{portfolioId}/positions/lookup`, `PATCH/DELETE /api/v1/portfolios/{portfolioId}/positions/{positionId}`                     |
| CSV import         | `POST /api/v1/portfolios/{portfolioId}/positions/imports/preview`, `POST /api/v1/portfolios/{portfolioId}/positions/imports/commit`                                                                        |
| Trading operations | `GET/POST /api/v1/portfolios/{portfolioId}/trading-operations`                                                                                                                                             |
| Market data        | `GET /api/v1/portfolios/{portfolioId}/market-data/quotes`, `GET /api/v1/portfolios/{portfolioId}/market-data/history`                                                                                      |
| Templates          | `GET/POST /api/v1/templates`, `GET/PATCH/DELETE /api/v1/templates/{templateId}`, `POST /api/v1/templates/compile`, `GET/POST /api/v1/templates/{templateId}/compile`, `GET /api/v1/templates/placeholders` |
| Reports            | `GET/POST /api/v1/reports`, `POST /api/v1/reports/compile/{templateId}`, `POST /api/v1/reports/upload`, `GET/PATCH/DELETE /api/v1/reports/{slug}`, `GET /api/v1/reports/{slug}/download`                   |

Template/report series use runtime inputs plus report metadata tags to resolve placeholders such as `reports.by_tag(inputs.analysis_tag).latest.content`. Report `source` values are `compiled`, `uploaded`, `external`, and `agent`; `external` is reserved for true external user/API reports. Historical agent-memory reports are report-domain records, not the canonical memory substrate.

## Agent-Platform API

| Resource                     | Routes                                                                                                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workflow packages            | `GET/POST /api/workflow-packages`, `GET/PATCH/DELETE /api/workflow-packages/{packageId}`, `GET /api/workflow-packages/{packageId}/manifest`, `POST /api/workflow-packages/validate-manifest`, `POST /api/workflow-packages/import`    |
| Package secret bindings      | `GET /api/workflow-packages/{packageId}/secret-bindings`, `PUT/DELETE /api/workflow-packages/{packageId}/secret-bindings/{key}`                                                                                                       |
| Package exports and launches | `GET /api/workflow-packages/{packageId}/export`, `POST /api/workflow-packages/{packageId}/preflight`, `GET /api/workflow-packages/{packageId}/launch`, `POST /api/workflow-packages/{packageId}/launches`                             |
| Scheduled Tasks              | `GET/POST /api/schedules`, `POST /api/schedules/preview`, `GET/PATCH/DELETE /api/schedules/{scheduleId}`, `POST /api/schedules/{scheduleId}/preview`, `POST /api/schedules/{scheduleId}/run-now`, `GET /api/schedules/{scheduleId}/fires` |
| Model connections            | `GET/POST /api/model-connections`, `GET/PATCH/DELETE /api/model-connections/{connectionId}`, `POST /api/model-connections/{connectionId}/connection-test`, `POST /api/model-connections/{connectionId}/capability-probe`              |
| Extensions                   | `GET /api/extensions`, `PATCH /api/extensions/{extensionKey}`                                                                                                                                                                         |
| Tools                        | `GET /api/tools`                                                                                                                                                                                                                      |
| Memory                       | `POST /api/memory`, `POST /api/memory/{memoryId}/detail`, `POST /api/memory/{memoryId}/revisions`, `POST /api/memory/{memoryId}/events`, `POST /api/memory/{memoryId}/actions/resolve`, `POST /api/memory/{memoryId}/actions/reflect` |
| Runs                         | `GET /api/runs`, `GET/DELETE /api/runs/{runId}`, `GET /api/runs/{runId}/rerun-draft`, `POST /api/runs/{runId}/reruns`, `GET /api/runs/{runId}/fork-draft?sourceInvocationId=...`, `POST /api/runs/{runId}/forks`                      |

Live package reads and writes do not include status. Package persistence stores dependency keys as artifact references; readiness endpoints evaluate those refs against live model connections, extension state, and package secret bindings. Deleting a package deletes its owned runs.

Model Connection payloads use `protocolProfile` as the live writable selector, with `openai_chat_completions` and `openai_responses` as shipped values. Backend `CompatibilityResolutionService` owns effective compatibility evidence for reads, preflight, runtime strategy selection, and run provenance. Public create/update requests accept writable connection identity, endpoint/model settings, `protocolProfile`, timeout, reasoning effort, and write-only `apiKey`; client-authored capabilities, policy fields, probe cache TTL, derived `apiStyle`, `compatibilityProfile`, and other compatibility truth are rejected rather than treated as authoritative. Reads include backend-derived capability states, policy fields, timeout, probe cache metadata, reachability-test metadata, and historical derived `apiStyle`; raw secrets are never returned.

## Workflow Packages, HTTP Operations, And Package Secrets

Workflow Packages use `signaldeck.workflowPackage/v1` YAML. Package-local refs stay local, model bindings use global Model Connection keys, tool grants use global server-declared tool keys, and workflow graph nodes currently ship as `kind: step`, `kind: sequence`, `kind: fanout`, `kind: loop`, and `kind: http`.

Package-local agent prompts own methodology. The Digital Oracle researcher package keeps its research policy in the `digital_oracle_researcher` agent `systemPrompt`, grants the local `digital_oracle_phase1_tools` capability profile, and reserves `demo/digital_oracle_researcher.yaml` as the final proven artifact path. This is package data, not a global skill or platform orchestration surface.

`kind: step` invokes a local package agent through `AgentExecutionService`. `kind: http` is the shipped non-agent operation node and compiles into runtime operation specs rather than fake agents. HTTP request fields may contain literal JSON values, input refs, prior-node output refs, or `${{ secrets.key }}` refs. Secret refs are valid only in HTTP `url`, `headers`, `query`, and `body` fields.

Package secret bindings are package-local encrypted values, not manifest/export data. Reads expose only key, package id, presence, and timestamps. Deletes remove live values without rewriting artifacts. Exports omit package secret binding rows and raw values.

`HttpOperationExecutionService` resolves inputs, prior outputs, and package secret values immediately before dispatch. Production defaults allow `GET` and `POST`, require HTTPS, block private networks, cap timeouts/request/response size, disable redirects, redact secret-backed request metadata, store bounded response metadata, and validate parsed JSON/text responses against `response.outputSchema`.

## Tools And Runtime Tool Boundaries

`/api/tools` is the core global read-only discovery host. Finance-owned tools appear only while `signaldeck.finance` is enabled. Platform-core memory tools remain visible when finance is disabled.

Current native runtime tools include quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, finance-owned report lookup, `signaldeck.memory.write`, and `signaldeck.memory.lookup`. Finance also owns the phase-1 Digital Oracle-backed tools `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup`. The retired `signaldeck_reports_write` function name is fail-closed at native dispatch and is not live catalog metadata, ownership plumbing, or MCP fallback.

`signaldeck.news.lookup` and `signaldeck.social_sentiment.lookup` are separate tools. Social sentiment accepts one symbol, optional `sources` of `reddit` and `stocktwits`, optional date bounds, and `itemLimit` up to `50`, returning source blocks, aggregate metrics, and warnings.

The Digital Oracle-backed phase-1 tools expose normalized finance payloads only. `signaldeck.prediction_markets.lookup` reads prediction-market events and contracts from finance-owned lookups, `signaldeck.sec_filings.lookup` reads SEC filing summaries by ticker, and `signaldeck.market_sentiment.lookup` reads the `fear_greed` indicator. All three serialize camelCase result models with `warnings[]`; provider internals, package secrets, EDGAR contact config, raw payloads, and speculative phase-2 providers are not public contracts.

Tool failure metadata is typed with `failureClass`, `source`, `phase`, `retryable`, and `disposition`. The retryable allowlist is limited to pre-dispatch provider tool-argument JSON/object failures, native tool argument validation, and MCP argument JSON/schema validation before transport dispatch. Auth, permission, grants, namespaces, extension-disabled states, missing secrets, unsupported or retired tool names, provider/network/transport errors, MCP transport errors, executor/business-rule failures, policy failures, output-schema failures, and retry-bound exhaustion are fatal.

Model-feedback retries use one bounded correction attempt and record redacted `toolCallRetries` metadata. Retry admission is based on typed taxonomy, not free-form error text, provider status text, or exception class names alone.

Transient provider retries are a separate live-execution contract under `graphMetadata.modelGateway.providerRetries`. They use `policy="transientProviderRetry/v1"`, `maxAttempts=3`, failed-attempt-only `attempts[]`, and `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. First-attempt success and first non-retryable failure omit `providerRetries` entirely. This metadata never overloads `toolCallRetries`, and provider retry stays limited to live Workflow Package execution. Model connection tests, capability probes, and Responses manual replay remain retry-free or protocol-repair paths outside this provider retry contract.

## Scheduled Tasks

Scheduled Tasks is a platform-core, package-first surface at `/scheduled-tasks` and `/api/schedules`. Each schedule targets one current Workflow Package and one workflow key, and due fires create ordinary queued Workflow Package runs with `scheduleId`, `scheduleFireId`, `scheduledFor`, and `scheduleReason` provenance. It is not a finance-owned route and it is not a legacy orchestration surface.

Recurrence v1 is structured. `interval` uses `every` plus `unit` values of `minutes`, `hours`, or `days`. `daily` uses `atLocalTime`. `weekly` uses unique `daysOfWeek` values plus `atLocalTime`. `monthly` uses unique `daysOfMonth` values plus `atLocalTime`; invalid dates for a month are skipped. Schedules require a valid IANA `timezone`. Local wall-clock recurrence is converted to UTC for storage and API timestamps. DST spring gaps roll forward to the next valid local minute, and DST fall repeated local times fire once at the earliest valid repeated instant. `nextFireAt` is server-owned and becomes `null` when no future occurrence remains or the schedule is paused.

Materialization honors `overlapPolicy` values of `skip` and `queue`. Skip records a skipped fire with `skipReason="schedule_overlap_active"` when a linked run is still queued or running. Misfire policy is `skip` or `catchUpOne`; `catchUpOne` materializes only the latest eligible missed occurrence inside `misfireGraceSeconds`, while skip records the latest missed occurrence with `skipReason="schedule_misfire_skipped"` and advances to the next future occurrence.

Scheduled inputs are JSON object templates, not scripts. The allowed placeholder namespaces are `schedule`, `fire`, `window`, `lastRun`, and `vars`. Supported fire fields include `scheduledFor`, `scheduledLocalDate`, `scheduledLocalTime`, and `scheduledLocalDateTime`. Exact placeholder strings preserve the resolved JSON value type; embedded placeholders render as strings. Missing values, unsupported expressions, array indexing, functions, filters, arithmetic, secrets, and environment access fail preview or materialization. Rendered parameters are validated against the workflow input schema before a run is queued. Fire rows persist rendered parameters for audit.

`POST /api/schedules/preview` renders an unsaved draft for a required `scheduledFor` instant without persisting fires or runs. `POST /api/schedules/{scheduleId}/preview` renders the stored schedule for the supplied `scheduledFor`, or for `nextFireAt` when omitted; a stored schedule with no next fire returns a not-ready preview. Detail reads intentionally omit `inputTemplate` and `templateVars`, so the current UI seeds the Inputs tab from the workflow schema and only saves an explicit overwrite after a ready preview.

`POST /api/schedules/{scheduleId}/run-now` requires `idempotencyKey` and `scheduledFor`, creates a manual fire through the same scheduled-run materialization path, and returns the compact queued run summary. Repeating the same schedule, scheduled time, and key returns the same fire and run. Paused schedules may run now and remain paused. The UI navigates to `/runs/:runId` for queue and execution evidence after run-now succeeds.

`GET /api/schedules/{scheduleId}/fires` returns paged fire history with status, reason, local scheduled fields, rendered parameters, skip or error details, and linked run id while the schedule exists. `DELETE /api/schedules/{scheduleId}` returns 204 with no body, removes the schedule and its fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Deleted schedule fire history is not a preserved live surface. Rerun and fork descendants are ordinary run lineage and stay governed by run lineage. Startup schema repair detaches legacy schedule rows from linked runs, backfills `scheduleProvenance` when resolvable, deletes obsolete schedule and fire rows, and no longer routes schedule cleanup through a destructive service path. OpenAPI and regression tests assert the 204 delete operation and removed-route absence.

## Runs, Scheduler, Reruns, And Forks

The launch surface is `/workflow-packages/:packageId/run`, labeled `Launch Workflow Package`. It reads launch metadata, runs preflight, posts selected workflow key plus `parameters`, creates a durable queued run, and polls backend-owned progress/queue state while the explicit scheduler worker materializes due Scheduled Tasks and claims queued runs.

Run detail includes `steps`, agent `invocations`, `operationInvocations`, `memoryArtifacts`, `memoryEvents`, `extensionDependencies`, `graphMetadata.modelGateway.failureTaxonomy`, bounded `toolCallRetries`, live-execution `providerRetries` when a transient provider retry happened, and `packageProvenance`. `toolCallRetries` records model-feedback correction for typed tool-call argument failures. `providerRetries` records provider create-call retries only, omits metadata on first-attempt success and first non-retryable failure, and includes `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. Run package provenance carries sanitized `resolvedModelConnections` from `ModelConnectionCompatibilityResolution` with protocol profile, model id, sanitized endpoint identity, backend-derived capabilities, policies, probe cache TTL, timeout, and `hasApiKey`; it never includes raw API keys, headers, or provider payloads.

Run progress uses `unit`, `terminalCount`, `totalCount`, and `percent`, with terminal runs reporting `percent: 100`. Queue explanations are nullable backend read models that explain serial package-lane blocking or worker capacity.

Rerun is the root-parameter descendant flow. Fork is the invocation-input descendant flow keyed by `sourceInvocationId`; it persists `run_forks`, copies upstream context, and treats `resumeStepIndex` as the execution boundary rather than the editable target.

## Core Memory Contract

SignalDeck memory is platform-core infrastructure for Workflow Package runs. Runtime tools are `signaldeck.memory.write` and `signaldeck.memory.lookup`; exact-id `signaldeck.memory.get` is deferred. `/api/memory` and `/memory` are platform-core explicit-private-scope surfaces, not finance routes and not generic CRUD.

Memory writes use neutral `kind`, `summary`, `content`, `subjectRefs`, `attributes`, scope, status, revision, and trusted provenance. Writes create immutable revisions or reuse an exact duplicate active revision. Shared-scope conflicts return retryable `memory_revision_conflict`.

Memory lookup is scoped. Runtime selectors may use scope, subject refs, kind, status, tags, query, limit, offset, and max characters. When runtime-tool selectors are omitted, the server falls back to current run/package/agent context instead of running unscoped global search.

Shared namespaces use `namespace` scope with keys shaped as `{ownerPackageKey}/{namespaceKey}`. Owner packages read and write their declared namespaces, while non-owner packages need explicit read or write grants. Wildcards, ownerless namespaces, global memory search, and cross-package private writes fail closed.

`/api/memory` accepts body-carried `accessContext` and exposes bounded workflows: list explicit-scope memory, load detail, list revisions, list events, resolve, and reflect. List requests require `visibility="explicit-scope"` with a concrete private scope. Detail, revision, event, and action requests authorize the stored memory scope before returning data or mutating status.

The browser `/memory` route requires a package key before issuing API calls. It supports optional workflow, agent, and run context plus explicit private scope selection. It does not accept browser-authored namespace declarations, namespace grants, or grant-visible namespace views. It renders canonical memory entries, detail, revisions, and events only for authorized scopes.

Model-visible memory outputs may include memory/revision ids, status, kind, summary, content, subject refs, attributes, scope, provenance, and warnings. They must not expose report identity, raw markdown, download URLs, or audit links. API and UI memory projections return canonical memory only and do not include finance-owned report-history rows.

## Runtime Input Help Text

Workflow package run input schemas can include JSON Schema `title` and `description` on supported nodes. `title` supplies generated form labels and `description` supplies generated help text. They are display metadata only and do not change runtime input JSON, value-entry encoding, validation semantics, workflow wiring, or package-local agent invocation.

Unsupported help mechanisms include YAML comments, `comment`, `x-signaldeck-*` metadata, `patternProperties`, `oneOf`, `allOf`, `if`, `then`, `else`, `not`, and schema-valued `additionalProperties`.

## Removed Surfaces

Workflow Packages are the only live platform authoring root. Removed global authoring routes include `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*`. They are not aliases or redirects.

Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, global Digital Oracle skills, `/api/skills`, and `/skills*` are not live product surfaces.

## CI And Verification

- `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Backend CI runs ruff, black, isort, mypy, and pytest after `uv sync --frozen`.
- Frontend CI runs lint, typecheck, build, unit tests, and Playwright after `pnpm install --frozen-lockfile`.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
