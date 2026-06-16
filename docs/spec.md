# Technical Specification

> Status: Live technical reference for the current branch.

## Overview

SignalDeck is a dual-stack FastAPI and React/Vite application with preserved finance workflows and a package-first agent platform. Backend JSON is camelCase externally and snake_case internally. Preserved finance routes live under `/api/v1` through the bundled `signaldeck.finance` extension; platform routes live under `/api`.

The canonical execution model is immutable Workflow Package artifact plus late-bound execution environment. A run freezes the selected package artifact and non-secret runtime profile evidence, while live credentials, extension state, package secret bindings, provider behavior, and runtime infrastructure remain late-bound for readiness and execution.

## Runtime Topology

- Root startup is managed by `start.sh`, which wraps the root `docker-compose.yml` local/demo stack. Compose starts PostgreSQL/pgvector in `db` and the combined Nginx/FastAPI/scheduler app image in `app`.
- The public local app is `http://localhost:${APP_PORT:-8080}`. Nginx proxies `/health`, `/ready`, `/api/`, and `/api/v1/` to the internal backend; PostgreSQL and FastAPI are not exposed directly on host ports by default.
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
- `backend/app/extensions/signaldeck_finance/` contributes current finance/product/provider routes, finance tools, hooks, and registrars as `signaldeck.finance`.
- `backend/app/extensions/signaldeck_digital_oracle/` contributes only Digital Oracle runtime tools as `signaldeck.digital_oracle`; it adds no API routers, frontend routes, nav, provider bundles, or lifecycle hooks in this upgrade.
- `backend/app/api/dependencies.py` is the service composition root.
- `backend/app/core/telemetry.py` owns optional Logfire setup and trace/span id formatting.
- `backend/app/db/` owns PostgreSQL session lifecycle and startup schema repair.

## Frontend Architecture

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- `frontend/src/routes.ts` defines flat routes for dashboard, portfolios, templates, reports, Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Runs, and Memory. Tools are linked through package authoring metadata, not a standalone route.
- `frontend/src/components/layout.tsx` owns sidebar labels, breadcrumbs, and the app shell.
- `frontend/src/extensions/runtime-helpers.ts` assembles finance routes/nav from extension state and filters package-authoring tools across bundled frontend extensions; `ExtensionRead` is the slim `{key,label,enabled}` contract.
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
| Memory                       | `GET /api/memory/proposals`, `POST /api/memory/proposals/{proposalId}/actions/approve`, `POST /api/memory/proposals/{proposalId}/actions/reject`, `GET /api/memory/audit-events`, `GET /api/memory/quarantine` |
| Runs                         | `GET /api/runs`, `GET/DELETE /api/runs/{runId}`, `GET /api/runs/{runId}/rerun-draft`, `POST /api/runs/{runId}/reruns`, `GET /api/runs/{runId}/fork-draft?sourceInvocationId=...`, `POST /api/runs/{runId}/forks`                      |

Live package reads and writes do not include status. Package persistence stores dependency keys as artifact references; readiness endpoints evaluate those refs against live model connections, extension state, and package secret bindings. Deleting a package deletes its owned runs.

Model Connection payloads use `protocolProfile` as the live writable selector, with `openai_chat_completions` and `openai_responses` as shipped values. Backend `CompatibilityResolutionService` owns effective compatibility evidence for reads, preflight, runtime strategy selection, and run provenance. Public create/update requests accept writable connection identity, endpoint/model settings, `protocolProfile`, timeout, reasoning effort, and write-only `apiKey`; client-authored capabilities, policy fields, probe cache TTL, derived `apiStyle`, `compatibilityProfile`, and other compatibility truth are rejected rather than treated as authoritative. Reads include backend-derived capability states, policy fields, timeout, probe cache metadata, reachability-test metadata, and historical derived `apiStyle`; raw secrets are never returned.

Model Connection `outputStrategyPolicy` is backend-owned compatibility truth. The live policy values are:

| Policy | Runtime behavior |
| --- | --- |
| `require_strict_schema` | Selects `strictJsonSchema` and fails when strict JSON-schema output is explicitly unsupported. |
| `prefer_strict_schema` | Selects `strictJsonSchema` unless strict output is explicitly unsupported; otherwise selects `jsonObjectWithValidation` when JSON-object output is available. This is the default policy. |
| `allow_json_object_validation` | Selects `jsonObjectWithValidation` and fails when JSON-object output is explicitly unsupported. |
| `allow_plain_text` | Selects `plainText` and bypasses structured output enforcement. |

Runtime output strategies are recorded in run metadata under `graphMetadata.modelGateway.selectedStrategies.outputStrategy`:

| Strategy | Enforcement |
| --- | --- |
| `strictJsonSchema` | Sends provider-native strict JSON schema format and expects the provider response to already be valid schema-shaped JSON. Invalid JSON fails the invocation. |
| `jsonObjectWithValidation` | Requests a JSON object, parses and validates it against the package output schema, and can issue bounded model-feedback correction when the output is invalid. |
| `plainText` | Requests or accepts normal text output without structured JSON validation. |

## Workflow Packages, HTTP Operations, And Package Secrets

Workflow Packages use `signaldeck.workflowPackage/v1` YAML. Package-local refs stay local, model bindings use global Model Connection keys, tool grants use global server-declared tool keys, and workflow graph nodes currently ship as `kind: step`, `kind: sequence`, `kind: fanout`, `kind: loop`, and `kind: http`.

Package-local agent prompts own methodology. The Digital Oracle researcher package keeps research policy in package-local agent `systemPrompt` text, grants the local `digital_oracle_phase1_tools` capability profile, and reserves `demo/digital_oracle_researcher.yaml` as the final proven artifact path. This is package data, not a global skill or platform orchestration surface.

`kind: step` invokes a local package agent through `AgentExecutionService`. `kind: http` is the shipped non-agent operation node and compiles into runtime operation specs rather than fake agents. HTTP request fields may contain literal JSON values, input refs, prior-node output refs, or `${{ secrets.key }}` refs. Secret refs are valid only in HTTP `url`, `headers`, `query`, and `body` fields.

Package secret bindings are package-local encrypted values, not manifest/export data. Reads expose only key, package id, presence, and timestamps. Deletes remove live values without rewriting artifacts. Exports omit package secret binding rows and raw values.

`HttpOperationExecutionService` resolves inputs, prior outputs, and package secret values immediately before dispatch. Production defaults allow `GET` and `POST`, require HTTPS, block private networks, cap timeouts/request/response size, disable redirects, redact secret-backed request metadata, store bounded response metadata, and validate parsed JSON/text responses against `response.outputSchema`.

## Tools And Runtime Tool Boundaries

`/api/tools` is the core global read-only discovery host.

- Finance tools appear only while the `signaldeck.finance` toggle is enabled.
- Digital Oracle tools appear only while the `signaldeck.digital_oracle` toggle is enabled.
- Workflow memory is platform-core middleware declared by Workflow Package YAML, not a server-declared runtime tool.

Current native runtime tools include quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, and Finance Workspace report lookup. `signaldeck.digital_oracle` owns the phase-1 Digital Oracle tools `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`; their tool keys are canonical owner-qualified contracts and their OpenAI function names are mechanical forms derived from those keys. Old direct core memory runtime tools are removed rather than compatibility aliases. The retired `signaldeck_reports_write` function name is fail-closed at native dispatch and is not live catalog metadata, ownership plumbing, or MCP fallback.

`signaldeck.finance.news.lookup` and `signaldeck.finance.social_sentiment.lookup` are separate finance-owned tools. Social sentiment accepts one symbol, optional `sources` of `reddit` and `stocktwits`, optional date bounds, and `itemLimit` up to `50`, returning source blocks, aggregate metrics, and warnings.

The Digital Oracle-backed phase-1 tools expose normalized payloads only. `signaldeck.digital_oracle.prediction_markets.lookup` reads prediction-market events and contracts, `signaldeck.digital_oracle.sec_filings.lookup` reads SEC filing summaries by ticker, and `signaldeck.digital_oracle.market_sentiment.lookup` reads the `fear_greed` indicator. All three serialize camelCase result models with `warnings[]`; provider internals, package secrets, EDGAR contact config, raw payloads, and speculative phase-2 providers are not public contracts.

Deferred Digital Oracle candidates are not registered tools, not `/api/tools` entries, and not live acceptance paths. The roadmap order is `signaldeck.rates.lookup` first, then broader macro/rates coverage, derivatives/crypto, CFTC positioning, and optional `yfinance`-backed options only after stable schemas and optional-dependency tests exist. Generic web search remains package-private MCP configuration inside Workflow Packages, for example a package-local Exa MCP grant, not a shipped global Digital Oracle tool.

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

Run detail includes `steps`, agent `invocations`, `operationInvocations`, `workflowMemoryEvidence`, `extensionDependencies`, `graphMetadata.modelGateway.failureTaxonomy`, bounded `toolCallRetries`, live-execution `providerRetries` when a transient provider retry happened, and `packageProvenance`. Legacy-shaped `memoryArtifacts` and `memoryEvents` stay empty during the workflow-memory cutover. `toolCallRetries` records model-feedback correction for typed tool-call argument failures. `providerRetries` records provider create-call retries only, omits metadata on first-attempt success and first non-retryable failure, and includes `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. Run package provenance carries sanitized `resolvedModelConnections` from `ModelConnectionCompatibilityResolution` with protocol profile, model id, sanitized endpoint identity, backend-derived capabilities, policies, probe cache TTL, timeout, and `hasApiKey`; it never includes raw API keys, headers, or provider payloads.

Run progress uses `unit`, `terminalCount`, `totalCount`, and `percent`, with terminal runs reporting `percent: 100`. Queue explanations are nullable backend read models that explain serial package-lane blocking or worker capacity.

Rerun is the root-parameter descendant flow. Fork is the invocation-input descendant flow keyed by `sourceInvocationId`; it persists `run_forks`, copies upstream context, and treats `resumeStepIndex` as the execution boundary rather than the editable target.

## Core Memory Contract

SignalDeck memory is platform-core workflow-runtime middleware for Workflow Package runs in a trusted single-user local/private deployment. Packages opt in through declarative `spec.memory`, workflow memory, agent memory, or step memory blocks. If memory is omitted, retrieval, proposals, and checkpoints stay disabled. The old direct runtime memory tools are removed; authors must not grant or call them.

The memory manifest contract has four blocks. `retrieval` accepts `enabled`, `namespaces`, `maxItems`, `relevanceThreshold`, and `includeKinds`. `writes` accepts `proposals`, `allowedKinds`, `defaultDecision`, and `autoCommitKinds`; commit defaults require non-empty safe auto-commit kinds that are included in `allowedKinds` and limited to `fact`, `observation`, and `preference`. `policy` accepts `secrets`, `sensitiveData`, `expirationDays`, `unauthorized`, and `consolidation`. `checkpoints` accepts `enabled` and `retention`.

Memory context is injected only as labelled non-authoritative model input reference data. It cannot override system, developer, or package instructions, and memory item content never belongs in model instructions. Retrieval filters by scope and lifecycle before ranking and excludes deleted, superseded, expired, unauthorized, quarantined, review-pending, legacy, and archive records.

Agents do not write memory directly. When `writes.proposals` is enabled, agents emit structured `memoryProposals` in their output. The proposal service stages proposals, and the workflow memory policy service is the only activation path. Secret detector hits reject or quarantine before activation; sensitive detector hits require review or quarantine and cannot auto-commit.

`/api/memory` is retained as trusted platform-core review infrastructure for proposals, approve/reject actions, audit-event reads, and quarantine reads. It is not a direct runtime write/lookup API, not a finance route, not public multi-user CRUD, and not an authorization surface. Finance report history and `signaldeck.finance.reports.lookup` remain report-domain behavior, not canonical workflow memory.

Checkpoints are run-local recovery/state artifacts governed by `checkpoints.enabled` and `retention`. They use separate checkpoint persistence and evidence from long-term memory items, proposals, decisions, audit events, revisions, quarantine, and consolidation records.

Run detail exposes `workflowMemoryEvidence` sourced from middleware metadata, proposals, decisions, quarantine, audit events, active items, and checkpoints. Model-visible memory outputs must not expose report identity, download URLs, raw markdown, arbitrary attributes, runtime tags, chunks, embeddings, vector scores, or old tool-call audit links.

Old memory tables and chunk/embedding tables are startup-repair or legacy-isolation concerns only. They are not live runtime, admin, API, UI, or tool contracts, and there is no compatibility reader or automatic promotion into workflow memory.

## Runtime Input Semantics

Workflow Package runtime inputs are workflow-scoped JSON object payloads. The launch page, Scheduled Tasks, reruns, forks, and saved runtime input presets all converge on the same canonical validation rules before a payload is persisted or used to queue work.

For supported object schemas, the Web UI uses the generated schema form as the primary editing surface. Required fields and fields with schema defaults are active immediately. Optional inputs without defaults stay visible as Add Field rows, so operators can discover them without adding keys to the payload. They are omitted until the operator explicitly includes them. JSON Schema `title` supplies generated form labels, and `description` supplies generated help text. These are display metadata only and do not change runtime input JSON, validation, workflow wiring, or package-local agent invocation.

Absent, `JSON null`, and `empty string` are distinct values. An absent optional key means the key is not part of the canonical payload. `JSON null` is accepted only when the input schema declares the narrow nullable form `type: [T, "null"]` or `type: ["null", T]`; explicit null is rejected for non-nullable fields. Blank optional form controls do not become null. If a string field is included and its value is `""`, the empty string is a real string value and is preserved. Schema defaults materialize intentionally in canonical payloads when the schema provides them.

Advanced JSON is a secondary editing mode for supported schemas and the fallback for unsupported schemas. It lets operators inspect or edit the raw object payload, but it never bypasses validation. Before preflight, launch, save, or overwrite, the UI parses Advanced JSON and validates it into the canonical form state. Invalid JSON, non-object payloads, or local schema mismatches block those actions before any API call is made.

Saved runtime input presets persist named canonical payload presets for one package workflow. Creating or updating a saved runtime input preset validates the payload against the current workflow input schema and stores the canonical result. Name-only updates preserve the existing payload. When a saved runtime input preset is stale or incompatible with the current schema, the UI keeps it visible for review instead of silently mutating or dropping fields.

The backend is the canonical persistence boundary. Launches, scheduled preview and materialization, reruns, forks, and saved runtime input preset create/update paths share canonical workflow input validation: absent optional no-default fields stay absent, defaults materialize, explicit nullable nulls are preserved only for declared nullable fields, non-nullable nulls fail validation, and empty strings remain strings. Run snapshots and saved presets persist the canonical payload rather than raw editor text.

Unsupported help and schema mechanisms include YAML comments, `comment`, `x-signaldeck-*` metadata, `patternProperties`, `oneOf`, `allOf`, `if`, `then`, `else`, `not`, and schema-valued `additionalProperties`.

## Removed Surfaces

Workflow Packages are the only live platform authoring root. Removed global authoring routes include `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*`. They are not aliases or redirects.

Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, global Digital Oracle skills, `/api/skills`, and `/skills*` are not live product surfaces.

## CI And Verification

- `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Backend CI runs ruff, black, isort, mypy, and pytest after `uv sync --frozen`.
- Frontend CI runs lint, typecheck, build, unit tests, and Playwright after `pnpm install --frozen-lockfile`.
- Automated CI must use fakes, fixtures, deterministic providers, and local descriptors only. It must not call live provider APIs, live MCP web search, or `yfinance` network paths.
- Upstream/provider live regression is manual and dev-only. Evidence from fixture refreshes, provider smoke checks, or live MCP validation is captured outside CI.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
