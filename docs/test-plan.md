# Test Plan

> Status: Live automated-coverage reference for branch `feature/memory` at `51d748b`.

## Backend Quality Gates

- `uv run ruff check app tests`
- `uv run black --check app tests`
- `uv run isort --check-only app tests`
- `uv run mypy app`
- `uv run pytest`

Backend coverage must prove preserved `/api/v1` finance CRUD, template/report behavior, package-first platform contracts, backend-owned compatibility resolution, Model Gateway behavior, native runtime tools, typed tool-failure taxonomy, bounded retries, memory services, explicit-private-scope `/api/memory`, scheduler semantics, run provenance, and removed-route guarantees.

## Frontend Quality Gates

- `pnpm lint`
- `pnpm typecheck`
- `pnpm build`
- `pnpm test:run`
- `pnpm test:e2e`

Frontend coverage must prove API helpers, query keys, formatting helpers, portfolio analytics, template/report flows, Workflow Package authoring, package secret bindings, dedicated launch page behavior, Model Connections, Extensions, server-declared Tools metadata in package authoring, Runs, run detail evidence, memory evidence rendering, explicit-private-scope `/memory`, and removed-route absence.

## Contract Coverage Matrix

| Surface                      | Required coverage                                                                                                                                                                                                                                                                |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API conventions              | Error envelope shape, camelCase aliases, decimal string serialization, multipart upload routes, and `422` validation behavior.                                                                                                                                                   |
| Preserved finance routes     | Portfolio, balance, position, CSV import, trade, quote/history, template, and report route families under `/api/v1`.                                                                                                                                                             |
| Extension state              | `GET/PATCH /api/extensions` exposes only `key`, `label`, and `enabled`; finance-owned routes/nav/tools are hidden when disabled while platform-core memory tools remain visible.                                                                                                 |
| Workflow Packages            | YAML parser rejects aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate refs, raw ids, and unsupported `spec.skills`; package reads/writes do not expose live status.                                                                                  |
| Package secrets and HTTP ops | Secret binding CRUD masks values; HTTP nodes allow only supported methods, keep secrets in request fields only, redact metadata, validate responses, and persist operation invocation rows.                                                                                      |
| Model Connections            | Protocol profile validation, strict rejection of public compatibility/policy writes, backend-owned compatibility resolution, secret preservation/rotation, reachability test, capability probe cache, policy defaults, and secret-safe reads/errors.                             |
| Tools                        | Server-declared `/api/tools` catalog, extension filtering, OpenAI function names, finance-owned data tools, social sentiment, report lookup, retired `signaldeck_reports_write` fail-closed behavior, typed failure taxonomy, bounded retry metadata, and platform memory tools. |
| Runs                         | Launch, scheduler queue semantics, progress read model, run-owned package snapshots, resolved model runtime profile provenance, rerun, fork, operation cards, extension dependencies, trace/span ids, memory evidence, typed failure taxonomy, and bounded retry evidence.       |
| Runtime inputs               | JSON Schema `title` and `description` render as display metadata only; unsupported help-text/schema mechanisms remain rejected or ignored according to schema rules.                                                                                                             |
| Memory                       | Core schemas, write/reuse/supersede semantics, scoped lookup fallback, namespace grants, conflict handling, runtime tools, `/api/memory`, `/memory`, run memory events, and report-domain separation.                                                                            |
| Removed surfaces             | Backend and frontend absence for `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, backtests, and removed global authoring routes.                                                                                                              |

## Backend Test Scope

Backend tests cover preserved `/api/v1` CRUD, templates, reports, artifact-only workflow package dependency persistence, launch/preflight readiness, capability-aware model-connection probes, protocol-profile validation, strict public compatibility-write rejection, backend-owned compatibility resolution, scoped package requirements, rerun/fork draft readiness, package import/export with inline private MCP `env`, `headers`, and `query`, package secret bindings, HTTP operation execution, model connections, slim bundled extension state, extension-filtered tools, Model Gateway adapter execution, structured-output strategy selection, typed tool-failure taxonomy, bounded tool-call retry behavior, native tool-call capability enforcement, provider error normalization, frozen run-owned runtime-profile provenance, backend-owned run progress and queue read models, explicit scheduler worker semantics, dependency-only run extension records, ref-based invocation payloads, runtime tools, core memory schemas/services/tools, package-qualified memory scopes, namespace grants, `/api/memory`, shared-memory conflicts, persisted run memory evidence, trace metadata, global runs, DB upgrades, retired `signaldeck_reports_write` fail-closed behavior, and removed-route guarantees.

## Frontend Test Scope

Frontend tests cover API helpers, query keys, formatting helpers, markdown formatting, portfolio analytics, workflow package helpers, authoring-only package editor flows, package secret binding UI, Model Connections protocol-profile editing, backend-derived compatibility evidence rendering, separate reachability-test and capability-probe actions, dedicated launch page behavior, capability blocker and warning rendering, backend progress/queue consumption, rerun/fork current-readiness gating, run-detail operation cards, effective runtime-profile rendering, typed failure/retry evidence, memory evidence rendering, explicit-private-scope `/memory`, layout routing, and browser E2E route families.

## E2E Scope

Playwright uses Chromium only. `frontend/playwright.config.ts` starts a dedicated backend on `8001` and built frontend preview on `4173`.

The backend helper starts the explicit run scheduler worker alongside Uvicorn for the Playwright run and defaults `QUOTE_PROVIDER_BACKEND=deterministic`. The frontend helper builds first, previews with `--strictPort`, and defaults `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`.

Specs use API-assisted setup when it keeps UI assertions focused. Preserved product setup uses `/api/v1`; platform setup uses `/api`.

Route-family coverage includes smoke/navigation, portfolio CRUD, reports/templates, the `/extensions` state page, Workflow Packages, Model Connections, Runs, `/memory`, run detail fixtures, package import/export flows, package secret bindings, authoring-only package editor behavior, the dedicated `/workflow-packages/:packageId/run` page labeled `Launch Workflow Package`, extension enable/disable gating, and the TradingAgents smoke package as ordinary demo data.

Compatibility E2E coverage uses deterministic or fake OpenAI-compatible providers for strict schema, JSON-object fallback, missing native tool-call support, unsupported reasoning fields, and missing usage metadata without live external network dependencies.
Frontend removed-route assertions cover `/templates/seed`, `/tryout*`, `/studio*`, `/orchestration*`, `/backtests*`, hidden removed navigation entries, and absence of live global-authoring routes from the router. Backend removed-surface coverage separately guards `/api/skills` and removed global-authoring API families.

## Focused Verification Targets

Use targeted checks when these contracts change:

```bash
(cd backend && uv run pytest tests/test_workflow_package_preflight.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_runtime_tools.py tests/test_mcp_runtime.py tests/test_memory_domain_schemas.py tests/test_memory_service.py tests/test_api_memory.py tests/test_runtime_db_upgrades.py tests/test_legacy_backend_cutover.py)
(cd frontend && pnpm test:run src/pages/workflow-packages src/pages/model-connections src/pages/runs src/pages/memory src/routes.test.tsx src/platform-clean-break.test.ts)
```

## Extension Metadata Absence Guard

The final cleanup guard searches live code, docs, and AGENTS files for removed public extension metadata names. Allowed matches are destructive upgrade code, explicit negative-validation tests, upgrade-normalization tests, and private initial-enabled seed wiring. Live docs and AGENTS files are not exceptions.

```bash
rg -n "disabled""Reason|disabled_""reason|state""Version|state_""version|contribution""Categories|contribution_""categories|versioning""Rule|versioning_""rule|default""Enabled|default_""enabled|Extension""ContributionRead|extension""Snapshots|extension_""snapshots|Run""ExtensionSnapshotRead" backend frontend docs AGENTS.md -g '!frontend/retired/**' -g '!frontend/dist/**' -g '!backend/.venv/**' -g '!backend/.mypy_cache/**' -g '!backend/.pytest_cache/**'
```
