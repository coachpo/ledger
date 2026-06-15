# Test Plan

> Status: Live automated-coverage reference for branch `main` at `6c40d44`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend coverage must prove preserved `/api/v1` finance CRUD, template/report behavior, package-first platform contracts, Scheduled Tasks API and materialization semantics, backend-owned compatibility resolution, Model Gateway behavior, native runtime tools, Digital Oracle phase-1 tools owned by `signaldeck.digital_oracle`, typed tool-failure taxonomy, bounded `toolCallRetries`, distinct live-execution `providerRetries`, memory services, lean scoped runtime `/api/memory`, trusted operator `/api/memory/admin/entries*`, scheduler semantics, run provenance, and removed-route guarantees.

Automated backend coverage must stay deterministic. CI uses fake clients, fixtures, deterministic provider settings, and descriptor assertions only; it must not call live provider APIs, live MCP web search, or `yfinance` network paths. Fixture refreshes, live provider smoke checks, and upstream/provider regression runs are manual/dev-only checks, with evidence captured outside CI.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend coverage must prove API helpers, query keys, formatting helpers, portfolio analytics, template/report flows, Workflow Package authoring, package secret bindings, dedicated launch page behavior, Scheduled Tasks inventory/detail/create/input-preview/history/run-now flows, Model Connections, Extensions, server-declared Tools metadata in package authoring, independent filtering for extension-owned tool choices, Runs, run detail evidence, memory evidence rendering, trusted operator `/memory` admin behavior, and removed-route absence.

## Contract Coverage Matrix

| Surface                      | Required coverage                                                                                                                                                                                                                                                                |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API conventions              | Error envelope shape, camelCase aliases, decimal string serialization, multipart upload routes, and `422` validation behavior.                                                                                                                                                   |
| Preserved finance routes     | Portfolio, balance, position, CSV import, trade, quote/history, template, and report route families under `/api/v1`.                                                                                                                                                             |
| Extension state              | `GET/PATCH /api/extensions` exposes only `key`, `label`, and `enabled`; bundled extension routes/nav/tools are hidden by their own toggles while platform-core memory tools remain visible. |
| Workflow Packages            | YAML parser rejects aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate refs, raw ids, and unsupported `spec.skills`; package-local `systemPrompt` methodology stays in package artifacts; package reads/writes do not expose live status.             |
| Scheduled Tasks              | `/api/schedules` CRUD, list filters, 204 delete response, removed-route absence, retained direct run history, preserved run-linked artifacts through `scheduleProvenance`, startup repair detachment, structured recurrence, timezone and DST cases, overlap and misfire policy outcomes, input placeholder rendering, preview validation without persistence, run-now idempotency, fire history while the schedule exists, and linked run provenance. |
| Package secrets and HTTP ops | Secret binding CRUD masks values; HTTP nodes allow only supported methods, keep secrets in request fields only, redact metadata, validate responses, and persist operation invocation rows.                                                                                      |
| Model Connections            | Protocol profile validation, strict rejection of public compatibility/policy writes, backend-owned compatibility resolution, secret preservation/rotation, reachability test, capability probe cache, policy defaults, and secret-safe reads/errors.                             |
| Tools                        | Server-declared `/api/tools` catalog, extension filtering, canonical owner-qualified tool keys, mechanical OpenAI function names derived from those keys, Finance Workspace data tools, Digital Oracle-owned `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, report lookup, retired report-write fail-closed behavior, typed failure taxonomy, bounded `toolCallRetries`, platform memory tools, and absence of deferred Digital Oracle candidates such as `signaldeck.rates.lookup`. |
| Runs                         | Launch, scheduler queue semantics, progress read model, run-owned package snapshots, approved model runtime profile provenance, rerun, fork, operation cards, extension dependencies, trace/span ids, memory evidence, typed failure taxonomy, bounded `toolCallRetries`, and live-execution `providerRetries` with `terminalOutcome` only for `succeededAfterRetry` or `exhausted`.       |
| Runtime inputs               | JSON Schema `title` and `description` render as display metadata only; unsupported help-text/schema mechanisms remain rejected or ignored according to schema rules.                                                                                                             |
| Memory                       | Lean core schemas, write/reuse semantics, scoped workflow-visible lookup fallback, backend-enforced namespace grants, conflict handling, runtime tools, trusted operator admin APIs, `/memory` admin behavior, all-entry admin visibility, `visibleToWorkflow` filtering, admin-only revision/event history, admin-only single-entry hard delete, canonical revision cascade cleanup, typed run memory event snapshots, scope/provenance rules, no runtime revisions or events, no runtime tags, no arbitrary attributes, no chunk or embedding live contract, no runtime or bulk delete, and report-domain separation. |
| Removed surfaces             | Backend and frontend absence for `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtests, and removed global authoring routes.                                                                                                              |

## Backend Test Scope

Backend tests cover preserved `/api/v1` CRUD, templates, reports, artifact-only workflow package dependency persistence, launch/preflight readiness, capability-aware model-connection probes, protocol-profile validation, strict public compatibility-write rejection, backend-owned compatibility resolution, scoped package requirements, Digital Oracle package grants, package-local prompt methodology, rerun/fork draft readiness, package import/export with secret-bearing private MCP `env`, `headers`, and `query` omitted from export/read previews, package secret bindings, HTTP operation execution, Scheduled Tasks API CRUD, scheduled preview, run-now, 204 delete response, retained direct run history, preserved run-linked artifacts through `scheduleProvenance`, removed-route absence, fire history while the schedule exists, recurrence and DST materialization, overlap and misfire handling, input-template validation, model connections, slim bundled extension state for both bundled extensions, independently extension-filtered tools, Model Gateway adapter execution, structured-output strategy selection, typed tool-failure taxonomy, bounded `toolCallRetries`, native tool-call capability enforcement, Digital Oracle runtime tool behavior under `signaldeck.digital_oracle`, provider error normalization, live-execution `providerRetries` with omission on first-attempt success and first non-retryable failure, frozen run-owned runtime-profile provenance, backend-owned run progress and queue read models, explicit scheduler worker semantics, dependency-only run extension records, ref-based invocation payloads, runtime tools, core memory schemas/services/tools, package-qualified memory scopes, namespace grants, `/api/memory`, shared-memory conflicts, persisted run memory evidence, trace metadata, global runs, DB upgrades including schedule repair detachment, retired `signaldeck_reports_write` fail-closed behavior, and removed-route guarantees. T17 will promote and prove the final `demo/digital_oracle_researcher.yaml` artifact; T16 keeps this plan docs-only.

## Frontend Test Scope

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, workflow package helpers, authoring-only package editor flows, package secret binding UI, Scheduled Tasks hooks, list filters and row actions, detail recurrence editing, explicit scheduled-input preview and save overwrite behavior, fire-history panels, run-now navigation to run detail, delete confirmation and detail redirect behavior, Model Connections protocol-profile editing, backend-derived compatibility evidence rendering, separate reachability-test and capability-probe actions, dedicated launch page behavior, capability-profile tool choices from `/api/tools`, independent finance and Digital Oracle mixed-state filtering for extension-owned tool keys, capability blocker and warning rendering, backend progress/queue consumption, rerun/fork current-readiness gating, run-detail operation cards, effective runtime-profile rendering, typed failure/retry evidence, shared run-type mirroring for distinct `providerRetries` and `toolCallRetries`, memory evidence rendering, trusted operator `/memory` admin create/visibility/single-entry delete flows, no Memory Admin bulk-delete controls, layout routing, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper starts the explicit run scheduler worker alongside Uvicorn for the Playwright run and defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, the `/extensions` state page, Workflow Packages, Scheduled Tasks, Model Connections, Runs, `/memory`, run detail fixtures, package import/export flows, package secret bindings, authoring-only package editor behavior, the dedicated `/workflow-packages/:packageId/run` page labeled `Launch Workflow Package`, extension enable/disable gating, and the TradingAgents smoke package as ordinary demo data. Memory E2E creates trusted operator memory, preserves visible/hidden filter coverage, verifies single-entry destructive delete cancellation/confirmation, checks deleted list/detail absence, and asserts no bulk delete or checkbox selection surface exists. Scheduled Tasks E2E creates a schedule through `/scheduled-tasks/new`, previews `fire.scheduledLocalDate`, `fire.scheduledLocalTime`, and `fire.scheduledLocalDateTime` placeholders for an `America/New_York` schedule, saves the schedule, pauses and resumes it, runs it now, checks the limited fire-history panel, follows the latest-run link to `/runs/:runId`, and verifies the delete flow returns the user to `/scheduled-tasks`.

Compatibility E2E coverage uses deterministic or fake OpenAI-compatible providers for strict schema, JSON-object fallback, missing native tool-call support, unsupported reasoning fields, and missing usage metadata without live external network dependencies.

Digital Oracle provider coverage uses local replay fixtures and fake JSON clients for Polymarket/Kalshi prediction markets, SEC filings, and Fear & Greed sentiment. Generic web search is validated only as package-private MCP descriptor/config handling, not as a live global Digital Oracle tool or CI web-search call.

Frontend removed-route assertions cover `/templates/seed`, `/tryout*`, `/studio*`, `/orchestration*`, `/backtests*`, hidden removed navigation entries, and absence of live global-authoring routes from the router. Backend removed-surface coverage separately guards `/api/skills` and removed global-authoring API families.

## Focused Verification Targets

Use targeted checks when these contracts change:

```bash
(cd backend && uv run pytest tests/test_workflow_package_preflight.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_runtime_tools.py tests/test_mcp_runtime.py tests/test_memory_domain_schemas.py tests/test_memory_service.py tests/test_api_memory.py tests/test_runtime_db_upgrades.py tests/test_legacy_backend_cutover.py)
(cd frontend && pnpm test:run src/pages/workflow-packages src/pages/scheduled-tasks src/pages/model-connections src/pages/runs src/pages/memory src/routes.test.tsx)
(cd frontend && pnpm exec playwright test e2e/scheduled-tasks.spec.ts)
(cd frontend && pnpm typecheck && pnpm test:run && cd ../backend && uv run pytest tests/test_workflow_package_preflight.py -k "digital_oracle" -q)
```

Core Memory docs alignment checks should prove the live owner docs describe lean `memory.write` and `memory.lookup`, `visibleToWorkflow`, backend-owned namespace grants, removed chunk/embedding contracts, and intentional absence language for arbitrary attributes, audit links, removed chunk/embedding tables, report-backed memory, and runtime revisions:

```bash
rg -n "memory.write|memory.lookup|visibleToWorkflow|namespace|chunk|embedding" docs/data-model.md docs/spec.md docs/requirements.md docs/test-plan.md
rg -n "attributes|auditLinks|agent_memory_chunks|agent_memory_embeddings|report-backed memory|runtime revisions" docs/data-model.md docs/spec.md docs/requirements.md docs/test-plan.md
```

Scheduled Tasks final-doc verification also checks live docs and route guidance for retention-contract drift, plus the broad build and backend suite:

```bash
(cd frontend && pnpm build && cd ../backend && uv run pytest)
```

Provider retry docs and type mirror verification checks the canonical owner docs, the untouched pending-design note, and targeted frontend stability:

```bash
grep -n "providerRetries\|toolCallRetries\|terminalOutcome" docs/spec.md docs/data-model.md docs/requirements.md docs/test-plan.md
git diff --quiet -- docs/pending-design/model-provider-transient-retry.md
(cd frontend && pnpm lint && pnpm typecheck && pnpm build && pnpm test:run src/pages/runs/detail.test.tsx src/pages/runs/detail-http-operations.test.tsx)
rg -n "providerRetries" frontend/src/lib/types/run.ts
```

Digital Oracle docs alignment must also keep `demo/digital_oracle_researcher.yaml` as the final artifact path, describe `signaldeck.digital_oracle` as the default-enabled tool-only bundled owner for the three phase-1 tools, and avoid adding any Digital Oracle route/nav surface. Deferred roadmap docs must keep `signaldeck.rates.lookup` as the first future candidate, followed by macro/rates, derivatives/crypto, CFTC positioning, and optional `yfinance`-backed options only after stable schemas and optional-dependency tests exist.

No-live-network policy checks for Digital Oracle work:

```bash
(cd backend && uv run pytest tests/test_tool_catalog_api.py -q)
(cd backend && uv run pytest tests/test_runtime_tools.py tests/test_mcp_runtime.py -q)
rg -n "live provider|web_search_exa|yfinance|signaldeck\.rates\.lookup" docs/spec.md docs/test-plan.md docs/requirements.md
```

## Extension Metadata Absence Guard

The final cleanup guard searches live code, docs, and AGENTS files for removed public extension metadata names. Allowed matches are destructive upgrade code, explicit negative-validation tests, upgrade-normalization tests, and private initial-enabled seed wiring. Live docs and AGENTS files are not exceptions.

```bash
rg -n "disabled""Reason|disabled_""reason|state""Version|state_""version|contribution""Categories|contribution_""categories|versioning""Rule|versioning_""rule|default""Enabled|default_""enabled|Extension""ContributionRead|extension""Snapshots|extension_""snapshots|Run""ExtensionSnapshotRead" backend frontend docs AGENTS.md -g '!frontend/retired/**' -g '!frontend/dist/**' -g '!backend/.venv/**' -g '!backend/.mypy_cache/**' -g '!backend/.pytest_cache/**'
```
