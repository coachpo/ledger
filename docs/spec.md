# Technical Specification

> Status: Live technical reference for the current branch.

## Overview

SignalDeck is a dual-stack FastAPI and React/Vite application with preserved finance template/report workflows and a package-first agent platform. Backend JSON is camelCase externally and snake_case internally. Preserved finance routes live under `/api/v1` through the bundled `signaldeck.finance` extension; platform routes live under `/api`.

The canonical execution model is immutable Workflow Package artifact plus late-bound execution environment. A run freezes the selected package artifact and non-secret runtime profile evidence, while live credentials, extension state, package secret bindings, provider behavior, and runtime infrastructure remain late-bound for readiness and execution.

## Runtime Topology

- Root startup uses `start.sh`, which wraps the root `docker-compose.yml` local/demo stack.
- The Compose public local app is `http://localhost:${APP_PORT:-8080}`. Nginx proxies `/health`, `/ready`, `/api/`, and `/api/v1/` to the internal backend; PostgreSQL and FastAPI are not exposed directly on host ports by default.
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
- `backend/app/api/platform_router.py` mounts `/api/workflow-packages`, `/api/schedules`, `/api/model-connections`, `/api/extensions`, `/api/tools`, and `/api/runs`.
- `backend/app/extensions/signaldeck_finance/` contributes current template/report routes, finance provider services, finance tools, and registrars as `signaldeck.finance`.
- `backend/app/extensions/signaldeck_digital_oracle/` contributes only Digital Oracle runtime tools as `signaldeck.digital_oracle`; Digital Oracle has no route or nav surface, and it adds no API routers, frontend routes, or provider bundles in this upgrade.
- `backend/app/api/dependencies.py` is the service composition root.
- `backend/app/core/telemetry.py` owns optional Logfire setup and trace/span id formatting.
- `backend/app/db/` owns PostgreSQL session lifecycle, `create_all` bootstrap, bundled package seeds, and startup recovery.

## Frontend Architecture

- `frontend/src/App.tsx` creates the TanStack Query client, theme provider, error boundary, and router provider.
- `frontend/src/routes.ts` defines flat routes for dashboard, finance workspace pages, Workflow Packages, Scheduled Tasks, Model Connections, Extensions, and Runs. Tools are linked through package authoring metadata, not a standalone route.
- `frontend/src/components/layout.tsx` owns sidebar labels, breadcrumbs, and the app shell.
- `frontend/src/extensions/runtime-helpers.ts` assembles finance routes/nav from extension state and filters package-authoring tools across bundled frontend extensions; `ExtensionRead` is the slim `{key,label,enabled}` contract.
- API helpers live under `frontend/src/lib/api/`; wire types live under `frontend/src/lib/types/`; query keys live in `frontend/src/lib/query-keys.ts`.
- Platform authoring helpers under `frontend/src/lib/platform-authoring/` keep schema/value/ref/manifest transforms out of routed pages.

## Preserved Finance Product API

`signaldeck.finance` is enabled by default and gates preserved product APIs. Extension state supports enable and disable only.

| Resource  | Routes                                                                                                                                                                                                     |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Templates | `GET/POST /api/v1/templates`, `GET/PATCH/DELETE /api/v1/templates/{templateId}`, `POST /api/v1/templates/compile`, `GET/POST /api/v1/templates/{templateId}/compile`, `GET /api/v1/templates/placeholders` |
| Reports   | `GET/POST /api/v1/reports`, `POST /api/v1/reports/compile/{templateId}`, `POST /api/v1/reports/upload`, `GET/PATCH/DELETE /api/v1/reports/{slug}`, `GET /api/v1/reports/{slug}/download`                   |

Template/report series use runtime inputs plus report metadata tags to resolve placeholders such as `reports.by_tag(inputs.analysis_tag).latest.content`. Report `source` values are `compiled`, `uploaded`, `external`, and `agent`; `external` is reserved for true external user/API reports. Agent-origin reports are report-domain records.

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
| Runs                         | `GET /api/runs`, `GET/DELETE /api/runs/{runId}`, `GET /api/runs/{runId}/rerun-draft`, `POST /api/runs/{runId}/reruns`                      |

Live package reads and writes do not include status. Package persistence stores dependency keys as artifact references; readiness endpoints evaluate those refs against live model connections, extension state, and package secret bindings. Deleting a package deletes its owned runs.

Model Connection payloads use `protocolProfile` as the live writable selector, with `openai_chat_completions` and `openai_responses` as shipped values. Backend `ModelConnectionResolutionService` owns effective capability evidence for reads, preflight, runtime strategy selection, and run provenance. Public create/update requests accept writable connection identity, endpoint/model settings, `protocolProfile`, timeout, reasoning effort, and write-only `apiKey`; client-authored capabilities, policy fields, probe cache TTL, derived `apiStyle`, and other capability/runtime-profile truth are rejected rather than treated as authoritative. Reads include backend-derived capability states, policy fields, timeout, probe cache metadata, reachability-test metadata, and historical derived `apiStyle`; raw secrets are never returned.

Model Connection `outputStrategyPolicy` is backend-owned capability and runtime-profile truth. The live policy values are:

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

Package-local agent prompts own methodology. The Digital Oracle researcher package keeps research policy in package-local agent `systemPrompt` text, grants only the local Digital Oracle capability profile, and reserves `demo/digital_oracle_researcher.yaml` as the final proven Digital-Oracle-only artifact path. The TradingAgents advisory demo is the Finance-only artifact at `demo/tradingagents_advisory_research.yaml`, with indicators, fundamentals, news, social sentiment, reports, and market data on Finance-owned tool keys. Mixed-extension TradingAgents research remains possible only as explicit package-level composition, not as a bundled demo contract, global skill, or platform orchestration surface; it should use `signaldeck.digital_oracle.macro_rates.lookup` and `signaldeck.digital_oracle.prediction_markets.lookup` by default unless prompts explicitly grant and use broader Digital Oracle tools.

`kind: step` invokes a local package agent through `AgentExecutionService`. `kind: http` is the shipped non-agent operation node and compiles into runtime operation specs rather than fake agents. HTTP request fields may contain literal JSON values, input refs, prior-node output refs, or `${{ secrets.key }}` refs. Secret refs are valid only in HTTP `url`, `headers`, `query`, and `body` fields.

Package secret bindings are package-local encrypted values, not manifest/export data. Reads expose only key, package id, presence, and timestamps. Deletes remove live values without rewriting artifacts. Exports omit package secret binding rows and raw values.

`HttpOperationExecutionService` resolves inputs, prior outputs, and package secret values immediately before dispatch. Production defaults allow `GET` and `POST`, require HTTPS, block private networks, cap timeouts/request/response size, disable redirects, redact secret-backed request metadata, store bounded response metadata, and validate parsed JSON/text responses against `response.outputSchema`.

## Tools And Runtime Tool Boundaries

`/api/tools` is the core global read-only discovery host.

- Finance tools appear only while the `signaldeck.finance` toggle is enabled.
- Digital Oracle tools appear only while the `signaldeck.digital_oracle` toggle is enabled.
- There is no server-declared memory tool surface.

Current native runtime tools include quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, and Finance Workspace report lookup. `signaldeck.digital_oracle` owns the Digital Oracle tools `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`; their tool keys are canonical owner-qualified contracts and their OpenAI function names are mechanical forms derived from those keys.

`signaldeck.finance.indicators.lookup` is the Finance-owned technical-analysis tool under the unchanged public key and OpenAI function name. It accepts one symbol, explicit `currentDate`, `startDate`, and `endDate`, bounded `rowLimit`, and an `indicators[]` selection list. Supported selection types are `sma`, `ema`, `rsi`, `macd`, `bollinger_bands`, `atr`, and `vwma`; moving averages, RSI, ATR, and VWMA use `window`, MACD uses `fastWindow`, `slowWindow`, and `signalWindow`, and Bollinger bands use `window` plus optional `standardDeviations`. Results keep the existing `rows[].values[]` pattern with `close` plus deterministic names such as `sma_20`, `ema_20`, `rsi_14`, `macd_12_26_9`, `macd_signal_12_26_9`, `macd_histogram_12_26_9`, `bollinger_upper_20_2`, `bollinger_middle_20_2`, `bollinger_lower_20_2`, `atr_14`, and `vwma_20`. Unavailable values serialize as `value: null` with `nullReason` of `warmup`, `insufficient_history`, or `provider_gap`; raw provider payloads are not exposed.

`signaldeck.finance.fundamentals.lookup` is the Finance-owned fundamentals tool under the unchanged public key and `signaldeck_finance_fundamentals_lookup` OpenAI function name. It accepts one symbol, optional `metricNames` from the bounded valuation, profitability, growth, leverage, dividend, and beta metric set, optional `statementTypes` of `income_statement`, `balance_sheet`, and `cash_flow`, optional `periods` of `annual`, `quarterly`, and `trailing_twelve_months`, and `statementLimit` up to `12`. Results preserve `metrics[]`, `statements[]`, and `warnings[]`, serialize camelCase fields deterministically, redact provider warning details, and never expose raw provider payloads or backend-private provider configuration. Provider-unavailable or empty coverage returns structured warnings while keeping the existing tool key and result envelope.

`signaldeck.finance.news.lookup` and `signaldeck.finance.social_sentiment.lookup` are separate finance-owned tools, not a combined sentiment surface. News accepts optional `symbols`, optional `query`, a bounded `scope` of `symbol`, `market`, or `global`, optional date bounds, and `itemLimit` up to `50`; runtime dispatch resolves Alpha Vantage credentials only from package/caller runtime secret `alpha_vantage_api_key`, preserves `items[]`, `symbols`, `query`, bounded dates, and `warnings[]`, and reports provider failures, empty coverage, truncation, unsupported query scope, and bounded global provider coverage through structured warnings. Social sentiment accepts one symbol, optional `sources` of `reddit` and `stocktwits`, optional date bounds, and `itemLimit` up to `50`, returning normalized Reddit and StockTwits source blocks, aggregate metrics, and structured warnings for unavailable, malformed, or partial provider coverage. Neither tool exposes raw provider payloads, request URLs containing secrets, API keys, Authorization headers, or backend-private provider configuration, and this migration adds no provider-settings UI route.

The Digital Oracle-backed tools expose normalized payloads only. `signaldeck.digital_oracle.prediction_markets.lookup` reads prediction-market events and contracts. Its existing `query`, `venues`, `itemLimit`, and `includeResolved` request shape remains stable, and callers may additionally set `includeOrderBook: true` plus optional `depthLimit` from `1` to `10` to request normalized contract-level `orderBook` depth. Returned contract `orderBook` objects contain bounded `bids[]`, `asks[]`, `spread`, and `depthLimit` fields when provider data supports them; unavailable, malformed, or one-sided depth is reported through stable `warnings[]` rather than raw venue payloads or ad hoc exceptions. `signaldeck.digital_oracle.sec_filings.lookup` reads SEC filing summaries by `ticker` or `cik`, preserves existing `formTypes`, `startDate`, `endDate`, and `itemLimit` filters, and may accept optional `query` to return normalized `searchHits[]` over filing-summary metadata. When `includeOwnershipTransactions` is true, the tool returns bounded Form 4-derived `ownershipTransactions[]` summaries with issuer, reporting owner, transaction date/code, acquired/disposed code, shares, price, and ownership nature when available. It remains a filing-summary/search/Form 4 summary tool, not a raw archive retrieval or generic SEC crawler; unavailable Form 4 coverage, stale archive-only submissions, provider failures, and empty search results are reported through `warnings[]`. `signaldeck.digital_oracle.market_sentiment.lookup` reads the `fear_greed` indicator.

`signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup` are shipped native Digital Oracle runtime tools. Their request parsers reject unsupported fields, normalize accepted inputs before dispatch, and return camelCase result models with `warnings[]`. Macro/rates reports missing optional FRED runtime secret `fred_api_key` or missing provider coverage as structured warnings. Crypto derivatives and CFTC positioning report empty, stale, truncated, unavailable, or provider-limited coverage through structured warnings. Options returns normalized option-chain data and reports missing optional `yfinance` dependency, unavailable symbols, and provider gaps through structured warnings. None of these tools expose raw provider payloads, provider internals, package secrets, EDGAR contact config, Authorization headers, or private MCP config.

Generic web search remains package-private MCP configuration inside Workflow Packages, for example a package-local Exa MCP grant, not a shipped global Digital Oracle tool. The shipped Digital Oracle tool surface is limited to the seven registered keys above.

Tool failure metadata is typed with `failureClass`, `source`, `phase`, `retryable`, and `disposition`. The retryable allowlist is limited to pre-dispatch provider tool-argument JSON/object failures, native tool argument validation, and MCP argument JSON/schema validation before transport dispatch. Auth, permission, grants, namespaces, extension-disabled states, missing secrets, unsupported or retired tool names, provider/network/transport errors, MCP transport errors, executor/business-rule failures, policy failures, output-schema failures, and retry-bound exhaustion are fatal.

Model-feedback retries use one bounded correction attempt and record redacted `toolCallRetries` metadata. Retry admission is based on typed taxonomy, not free-form error text, provider status text, or exception class names alone.

Transient provider retries are a separate live-execution contract under `graphMetadata.modelGateway.providerRetries`. They use `policy="transientProviderRetry/v1"`, `maxAttempts=3`, failed-attempt-only `attempts[]`, and `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. First-attempt success and first non-retryable failure omit `providerRetries` entirely. This metadata never overloads `toolCallRetries`, and provider retry stays limited to live Workflow Package execution. Model connection tests, capability probes, and Responses manual replay remain retry-free or protocol-repair paths outside this provider retry contract.

## Scheduled Tasks

Scheduled Tasks is a platform-core, package-first surface at `/scheduled-tasks` and `/api/schedules`. Each schedule targets one current Workflow Package and one workflow key, and due fires create ordinary queued Workflow Package runs with `scheduleId`, `scheduleFireId`, `scheduledFor`, and `scheduleReason` provenance. It is not a finance-owned route and it is not a legacy orchestration surface.

Recurrence v1 is structured. `interval` uses `every` plus `unit` values of `minutes`, `hours`, or `days`. `daily` uses `atLocalTime`. `weekly` uses unique `daysOfWeek` values plus `atLocalTime`. `monthly` uses unique `daysOfMonth` values plus `atLocalTime`; invalid dates for a month are skipped. Schedules require a valid IANA `timezone`. Local wall-clock recurrence is converted to UTC for storage and API timestamps. DST spring gaps roll forward to the next valid local minute, and DST fall repeated local times fire once at the earliest valid repeated instant. `nextFireAt` is server-owned and becomes `null` when no future occurrence remains or the schedule is paused.

Materialization honors `overlapPolicy` values of `skip` and `queue`. Skip records a skipped fire with `skipReason="schedule_overlap_active"` when a linked run is still queued or running. Misfire policy is `skip` or `catchUpOne`; `catchUpOne` materializes only the latest eligible missed occurrence inside `misfireGraceSeconds`, while skip records the latest missed occurrence with `skipReason="schedule_misfire_skipped"` and advances to the next future occurrence.

Scheduled inputs are JSON object templates, not scripts. The allowed placeholder namespaces are `schedule`, `fire`, `window`, `lastRun`, and `vars`. Supported fire fields include `scheduledFor`, `scheduledLocalDate`, `scheduledLocalTime`, and `scheduledLocalDateTime`. Exact placeholder strings preserve the resolved JSON value type; embedded placeholders render as strings. Missing values, unsupported expressions, array indexing, functions, filters, arithmetic, secrets, and environment access fail preview or materialization. Rendered parameters are validated against the workflow input schema before a run is queued. Fire rows persist rendered parameters for audit.

`POST /api/schedules/preview` renders an unsaved draft for a required `scheduledFor` instant without persisting fires or runs. `POST /api/schedules/{scheduleId}/preview` renders the stored schedule for the supplied `scheduledFor`, or for `nextFireAt` when omitted; a stored schedule with no next fire returns a not-ready preview. Detail reads intentionally omit `inputTemplate` and `templateVars`, so the current UI seeds the Inputs tab from the workflow schema and saves an explicit template update only after a ready preview.

`POST /api/schedules/{scheduleId}/run-now` requires `idempotencyKey` and `scheduledFor`, creates a manual fire through the same scheduled-run materialization path, and returns the compact queued run summary. Repeating the same schedule, scheduled time, and key returns the same fire and run. Paused schedules may run now and remain paused. The UI navigates to `/runs/:runId` for queue and execution evidence after run-now succeeds.

`GET /api/schedules/{scheduleId}/fires` returns paged fire history with status, reason, local scheduled fields, rendered parameters, skip or error details, and linked run id while the schedule exists. `DELETE /api/schedules/{scheduleId}` returns 204 with no body, removes the schedule and its fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Deleted schedule fire history is not a preserved live surface. Reruns store only a source-run link. OpenAPI and regression tests assert the 204 delete operation and schedule provenance.

## Runs, Scheduler, And Reruns

The launch surface is `/workflow-packages/:packageId/run`, labeled `Launch Workflow Package`. It reads launch metadata, runs preflight, posts selected workflow key plus `parameters`, creates a durable queued run, and polls backend-owned progress/queue state while the explicit scheduler worker materializes due Scheduled Tasks and claims queued runs.

Run detail includes `steps`, agent `invocations`, `operationInvocations`, `extensionDependencies`, `graphMetadata.modelGateway.failureTaxonomy`, bounded `toolCallRetries`, live-execution `providerRetries` when a transient provider retry happened, and `packageProvenance`. `toolCallRetries` records model-feedback correction for typed tool-call argument failures. `providerRetries` records provider create-call retries only, omits metadata on first-attempt success and first non-retryable failure, and includes `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. Run package provenance carries sanitized `resolvedModelConnections` from `ModelConnectionRuntimeProfile` with protocol profile, model id, sanitized endpoint identity, backend-derived capabilities, policies, probe cache TTL, timeout, and `hasApiKey`; it never includes raw API keys, headers, or provider payloads.

Run progress uses `unit`, `terminalCount`, `totalCount`, and `percent`, with terminal runs reporting `percent: 100`. Queue explanations are nullable backend read models that explain serial package-lane blocking or worker capacity.

Rerun is the root-parameter descendant flow.

## Runtime Input Semantics

Workflow Package runtime inputs are workflow-scoped JSON object payloads. The launch page, Scheduled Tasks, and reruns all converge on the same canonical validation rules before a payload is persisted or used to queue work.

For supported object schemas, the Web UI uses the generated schema form as the primary editing surface. Required fields and fields with schema defaults are active immediately. Optional inputs without defaults stay visible as Add Field rows, so operators can discover them without adding keys to the payload. They are omitted until the operator explicitly includes them. JSON Schema `title` supplies generated form labels, and `description` supplies generated help text. These are display metadata only and do not change runtime input JSON, validation, workflow wiring, or package-local agent invocation.

Absent, `JSON null`, and `empty string` are distinct values. An absent optional key means the key is not part of the canonical payload. `JSON null` is accepted only when the input schema declares the narrow nullable form `type: [T, "null"]` or `type: ["null", T]`; explicit null is rejected for non-nullable fields. Blank optional form controls do not become null. If a string field is included and its value is `""`, the empty string is a real string value and is preserved. Schema defaults materialize intentionally in canonical payloads when the schema provides them.

Advanced JSON is a secondary editing mode for supported schemas and the fallback for unsupported schemas. It lets operators inspect or edit the raw object payload, but it never bypasses validation. Before preflight or launch, the UI parses Advanced JSON and validates it into the canonical form state. Invalid JSON, non-object payloads, or local schema mismatches block those actions before any API call is made.

The backend is the canonical persistence boundary. Launches, scheduled preview and materialization, and reruns share canonical workflow input validation: absent optional no-default fields stay absent, defaults materialize, explicit nullable nulls are preserved only for declared nullable fields, non-nullable nulls fail validation, and empty strings remain strings. Run snapshots persist the canonical payload rather than raw editor text.

Unsupported help and schema mechanisms include YAML comments, `comment`, `x-signaldeck-*` metadata, `patternProperties`, `oneOf`, `allOf`, `if`, `then`, `else`, `not`, and schema-valued `additionalProperties`.

## Removed Surfaces

Workflow Packages are the only live platform authoring root. Removed global authoring routes include `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*`. They are not aliases or redirects.

Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, global Digital Oracle skills, `/api/skills`, and `/skills*` are not live product surfaces.

Workflow-memory governance is not a live product surface. `spec.memory`, workflow/agent/step memory blocks, `/api/memory/*`, workflow checkpoints, direct memory runtime tools, and `workflowMemoryEvidence` are removed rather than aliased or redirected.

Invocation-input run descendants are not a live product surface. The former draft/create APIs and persistence artifact are removed rather than aliased or redirected.

Saved runtime input presets and history are not live product surfaces. The former runtime-input registry APIs and persistence artifacts are removed rather than aliased or redirected.

## CI And Verification

- `version-sync` checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- Backend CI runs ruff, black, isort, mypy, and pytest after `uv sync --frozen`.
- Frontend CI runs lint, typecheck, build, unit tests, and Playwright after `pnpm install --frozen-lockfile`.
- Automated CI must use fakes, fixtures, deterministic providers, and local descriptors only. It must not call live provider APIs, live MCP web search, or `yfinance` network paths.
- Upstream/provider live regression is manual and dev-only. Evidence from fixture refreshes, provider smoke checks, or live MCP validation is captured outside CI.
- Docker image publishing builds backend and frontend linux/arm64 images for GHCR.
