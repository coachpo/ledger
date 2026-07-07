# Test Plan

> Status: Live automated-coverage reference for branch `main` at `6c40d44`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend coverage must prove preserved `/api/v1` finance CRUD, template/report behavior, package-first platform contracts, declarative workflow-memory middleware, Scheduled Tasks API and materialization semantics, backend-owned runtime-profile resolution, Model Gateway behavior, native runtime tools, Alpha Vantage/Yahoo-backed Finance news dispatch, Reddit and StockTwits social sentiment degradation, seven Digital Oracle tools owned by `signaldeck.digital_oracle`, typed tool-failure taxonomy, bounded `toolCallRetries`, distinct live-execution `providerRetries`, `/api/memory` proposal/audit/quarantine review surfaces, scheduler semantics, and run provenance.

Automated backend coverage must stay deterministic. CI uses fake clients, fixtures, deterministic provider settings, and descriptor assertions only; it must not call live provider APIs, live MCP web search, Alpha Vantage, Yahoo, Reddit, StockTwits, or `yfinance` network paths. Fixture refreshes, live provider smoke checks, and upstream/provider regression runs are manual/dev-only checks, with evidence captured outside CI.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend coverage must prove API helpers, query keys, formatting helpers, portfolio analytics, template/report flows, Workflow Package authoring, package secret bindings, dedicated launch page behavior, Scheduled Tasks inventory/detail/create/input-preview/history/run-now flows, Model Connections, Extensions, server-declared Tools metadata in package authoring, independent filtering for extension-owned tool choices, Runs, run detail evidence, memory evidence rendering, trusted operator `/memory` review behavior, and the product-owned unknown-route shell.

## Contract Coverage Matrix

| Surface                      | Required coverage                                                                                                                                                                                                                                                                |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API conventions              | Error envelope shape, camelCase aliases, decimal string serialization, multipart upload routes, and `422` validation behavior.                                                                                                                                                   |
| Preserved finance routes     | Portfolio, balance, position, CSV import, trade, quote/history, template, and report route families under `/api/v1`.                                                                                                                                                             |
| Extension state              | `GET/PATCH /api/extensions` exposes only `key`, `label`, and `enabled`; bundled extension routes/nav/tools are hidden by their own toggles while workflow memory remains platform-core middleware declared in package YAML. |
| Workflow Packages            | YAML parser rejects aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate refs, raw ids, unsupported `spec.skills`, invalid runtime tool grants, and prompt-like memory fields; package-local `systemPrompt` methodology stays in package artifacts.             |
| Scheduled Tasks              | `/api/schedules` CRUD, list filters, 204 delete response, retained direct run history, preserved run-linked artifacts through `scheduleProvenance`, structured recurrence, timezone and DST cases, overlap and misfire policy outcomes, input placeholder rendering, preview validation without persistence, run-now idempotency, fire history while the schedule exists, and linked run provenance. |
| Package secrets and HTTP ops | Secret binding CRUD masks values; HTTP nodes allow only supported methods, keep secrets in request fields only, redact metadata, validate responses, and persist operation invocation rows.                                                                                      |
| Model Connections            | Protocol profile validation, strict rejection of public runtime-profile/policy writes, backend-owned runtime-profile resolution, secret preservation/rotation, reachability test, capability probe cache, policy defaults, and secret-safe reads/errors.                             |
| Tools                        | Server-declared `/api/tools` catalog, extension filtering, canonical owner-qualified tool keys, mechanical OpenAI function names derived from those keys, Finance Workspace data tools, Digital Oracle-owned `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, `signaldeck.digital_oracle.options.lookup`, report lookup, typed failure taxonomy, and bounded `toolCallRetries`. |
| Runs                         | Launch, scheduler queue semantics, progress read model, run-owned package snapshots, approved model runtime profile provenance, rerun, fork, operation cards, extension dependencies, trace/span ids, `workflowMemoryEvidence`, typed failure taxonomy, bounded `toolCallRetries`, and live-execution `providerRetries` with `terminalOutcome` only for `succeededAfterRetry` or `exhausted`.       |
| Runtime inputs               | JSON Schema `title` and `description` render as display metadata only; unsupported help-text/schema mechanisms remain rejected or ignored according to schema rules.                                                                                                             |
| Memory                       | Declarative `spec.memory` parsing and compiled policy precedence, disabled-by-omission behavior, retrieval lifecycle exclusions, non-authoritative input-only context injection, proposal-first writes, policy-only activation, secret and sensitive detector handling, quarantine/review states, audit evidence, checkpoint separation, `/api/memory` proposal/audit/quarantine review APIs, and report-domain separation. |
| Routing fallback             | Unsupported frontend paths use the product-owned unknown-route shell; live backend route ownership is covered through API and OpenAPI tests.                                                                                                                                      |

## Backend Test Scope

Backend tests cover preserved `/api/v1` CRUD, templates, reports, artifact-only workflow package dependency persistence, launch/preflight readiness, declarative workflow-memory YAML and demo preflight, capability-aware model-connection probes, protocol-profile validation, strict public runtime-profile write rejection, backend-owned runtime-profile resolution, scoped package requirements, Digital Oracle package grants, package-local prompt methodology, rerun/fork draft readiness, package import/export with secret-bearing private MCP `env`, `headers`, and `query` omitted from export/read previews, package secret bindings, HTTP operation execution, Scheduled Tasks API CRUD, scheduled preview, run-now, 204 delete response, retained direct run history, preserved run-linked artifacts through `scheduleProvenance`, fire history while the schedule exists, recurrence and DST materialization, overlap and misfire handling, input-template validation, model connections, slim bundled extension state for both bundled extensions, independently extension-filtered tools, Model Gateway adapter execution, structured-output strategy selection, typed tool-failure taxonomy, bounded `toolCallRetries`, native tool-call capability enforcement, Digital Oracle runtime tool behavior under `signaldeck.digital_oracle`, provider error normalization, live-execution `providerRetries` with omission on first-attempt success and first non-retryable failure, frozen run-owned runtime-profile provenance, backend-owned run progress and queue read models, explicit scheduler worker semantics, dependency-only run extension records, ref-based invocation payloads, current runtime tools, workflow-memory middleware services, proposal/audit/quarantine `/api/memory` review APIs, persisted `workflowMemoryEvidence`, trace metadata, global runs, workflow-memory upgrade safety, and fail-closed runtime behavior.

## Frontend Test Scope

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, workflow package helpers, authoring-only package editor flows, package secret binding UI, Scheduled Tasks hooks, list filters and row actions, detail recurrence editing, explicit scheduled-input preview and save overwrite behavior, fire-history panels, run-now navigation to run detail, delete confirmation and detail redirect behavior, Model Connections protocol-profile editing, backend-derived capability evidence rendering, separate reachability-test and capability-probe actions, dedicated launch page behavior, capability-profile tool choices from `/api/tools`, independent finance and Digital Oracle mixed-state filtering for extension-owned tool keys, capability blocker and warning rendering, backend progress/queue consumption, rerun/fork current-readiness gating, run-detail operation cards, effective runtime-profile rendering, typed failure/retry evidence, shared run-type mirroring for distinct `providerRetries` and `toolCallRetries`, workflow-memory evidence rendering, proposal/audit/quarantine review UI behavior, layout routing, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper starts the explicit run scheduler worker alongside Uvicorn for the Playwright run and defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, the `/extensions` state page, Workflow Packages, Scheduled Tasks, Model Connections, Runs, Memory review, run detail fixtures, package import/export flows, package secret bindings, authoring-only package editor behavior, the dedicated `/workflow-packages/:packageId/run` page labeled `Launch Workflow Package`, extension enable/disable gating, and demo Workflow Packages as ordinary package data. Memory E2E verifies proposal, audit, quarantine, and workflow-memory evidence review behavior without reintroducing direct runtime write/lookup controls. Scheduled Tasks E2E creates a schedule through `/scheduled-tasks/new`, previews `fire.scheduledLocalDate`, `fire.scheduledLocalTime`, and `fire.scheduledLocalDateTime` placeholders for an `America/New_York` schedule, saves the schedule, pauses and resumes it, runs it now, checks the limited fire-history panel, follows the latest-run link to `/runs/:runId`, and verifies the delete flow returns the user to `/scheduled-tasks`.

Provider capability E2E coverage uses deterministic or fake OpenAI-compatible providers for strict schema, JSON-object fallback, missing native tool-call support, unsupported reasoning fields, and missing usage metadata without live external network dependencies.

Digital Oracle provider coverage uses local replay fixtures and fake JSON clients for Polymarket/Kalshi prediction markets, SEC filings, Fear & Greed sentiment, macro/rates, crypto derivatives, CFTC positioning, and options. Missing optional FRED runtime secret `fred_api_key` and missing optional `yfinance` dependency are warning-path fixtures, not CI failures or live-network calls. Generic web search is validated only as package-private MCP descriptor/config handling, not as a live global Digital Oracle tool or CI web-search call.

Frontend route tests cover the product-owned unknown-route shell instead of maintaining historical route matrices. Backend route coverage lives with the current API and OpenAPI tests.

## Focused Verification Targets

Use targeted checks when these contracts change:

```bash
(cd backend && uv run pytest tests/test_workflow_package_preflight.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_runtime_tools.py tests/test_mcp_runtime.py tests/test_memory_domain_schemas.py tests/test_memory_service.py tests/test_api_memory.py tests/test_db_bootstrap.py)
(cd frontend && pnpm test:run src/pages/workflow-packages src/pages/scheduled-tasks src/pages/model-connections src/pages/runs src/pages/memory src/routes.test.tsx)
(cd frontend && pnpm exec playwright test e2e/scheduled-tasks.spec.ts)
(cd frontend && pnpm typecheck && pnpm test:run && cd ../backend && uv run pytest tests/test_workflow_package_preflight.py -k "digital_oracle" -q)
```

Scheduled Tasks changes use the broad build and backend suite:

```bash
(cd frontend && pnpm build && cd ../backend && uv run pytest)
```

Digital Oracle and Finance provider changes use local runtime tests:

```bash
(cd backend && uv run pytest tests/test_tool_catalog_api.py -q)
(cd backend && uv run pytest tests/test_runtime_tools.py tests/test_mcp_runtime.py -q)
```
