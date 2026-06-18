# Audit Checklist

Use this as an executable checklist. For each item, inspect the cited file, symbol, or test and mark the result as pass, fail, or `needs code evidence`. Do not treat uncertainty as a reason to preserve legacy behavior.

## Backend Layering And Module Boundaries

- [ ] Confirm `backend/app/api/router.py::api_router` mounts `/api/v1` only from `get_bundled_extension_registry().list_api_router_contributions()`.
- [ ] Confirm `backend/app/api/platform_router.py::platform_router` mounts only platform routers: extensions, memory, model connections, tools, workflow packages, schedules, and runs.
- [ ] Confirm finance `/api/v1` route ownership stays in `backend/app/extensions/signaldeck_finance/api_routers.py` and is not duplicated in platform core.
- [ ] Confirm route handlers use `backend/app/api/dependencies.py` service factories rather than direct session/repository orchestration.
- [ ] Confirm removed backend route families remain absent with `backend/tests/test_legacy_backend_cutover.py`.

## Workflow Package Authoring/Validation

- [ ] Confirm `backend/app/api/workflow_packages.py` exposes create, update, validate, import, export, manifest, secret-binding, runtime-input, preflight, launch metadata, and launch routes as package-first platform APIs.
- [ ] Confirm `backend/app/services/workflow_package_manifest_parser.py` rejects unsupported YAML features, raw global ids, duplicate refs, forbidden secret/id keys, and `spec.skills`.
- [ ] Confirm `backend/app/models/workflow_package.py::WorkflowPackage` stores one current package artifact with `manifest_source`, `manifest_hash`, `package_definition`, `compiled_plan`, and `compiled_hash`.
- [ ] Confirm package-private agents, output schemas, capability profiles, MCP configs, and workflow graphs are artifact data, not global authoring rows.
- [ ] Confirm regression coverage in `backend/tests/test_workflow_package_api.py`, `backend/tests/test_workflow_package_preflight.py`, and frontend workflow-package tests covers validation and removed version/status behavior.

## Launch/Preflight/Runtime-Input Flow

- [ ] Confirm `backend/app/api/workflow_packages.py::preflight_workflow_package` delegates to `WorkflowPackageService.preflight_package` and returns readiness without executing a run.
- [ ] Confirm `backend/app/api/workflow_packages.py::get_workflow_package_launch` returns launch metadata through `WorkflowPackageService.get_launch`.
- [ ] Confirm `backend/app/api/workflow_packages.py::create_workflow_package_launch` delegates to `WorkflowPackageService.create_launch` and creates a queued run through `RunService.create_workflow_package_launch`.
- [ ] Confirm runtime-input registry behavior is workflow-scoped and staleness-aware in `backend/app/services/workflow_package_runtime_input_registry.py` and `backend/app/services/workflow_package_runtime_inputs.py`.
- [ ] Confirm launch UI coverage in `frontend/src/pages/workflow-packages/launch.test.tsx` includes generated inputs, raw JSON fallback, defaults, optional omissions, and validation feedback.

## Run Queue/Worker/Runtime Execution

- [ ] Confirm `backend/app/models/run.py::Run` restricts `target_kind` to `workflowPackage`, defaults `status` to `queued`, and persists `queued_at`, lease fields, heartbeat fields, schedule provenance, package provenance, and lineage fields.
- [ ] Confirm `backend/app/services/run_service.py::create_workflow_package_launch`, `_create_queued_rerun_run`, and `_create_queued_fork_run` create durable queued rows rather than executing inline.
- [ ] Confirm `backend/app/workers/run_scheduler.py::RunSchedulerWorker.run_once` and `_run_loop` recover stale leases, materialize due schedules, claim queued runs, heartbeat leases, and execute claimed runs.
- [ ] Confirm `backend/app/services/run_queue_service.py::RunQueueService` owns `claim_next_run`, `heartbeat_run`, `release_run_lease`, and `recover_stale_leases`.
- [ ] Confirm queue, lease, stale recovery, rerun, fork, and run-detail behavior in `backend/tests/test_workflow_package_runtime_api.py`, `backend/tests/test_workflow_package_run_contracts.py`, and `backend/tests/test_runtime_repositories.py`.

## Scheduled Tasks

- [ ] Confirm `backend/app/api/schedules.py` exposes package-first create, list, detail, update, delete, preview, run-now, and fire-history routes only under `/api/schedules`.
- [ ] Confirm recurrence, IANA timezone validation, overlap policy, misfire policy, `inputTemplate`, `templateVars`, run-now `idempotencyKey`, and fire DTOs live in `backend/app/schemas/schedule.py`.
- [ ] Confirm `backend/app/services/workflow_package_schedule_service.py` and `workflow_package_schedule_materializer.py` render scheduled inputs, create fires, queue ordinary runs, and preserve run-owned schedule provenance.
- [ ] Confirm `backend/app/services/workflow_package_schedule_inputs.py` limits placeholders to `schedule`, `fire`, `window`, `lastRun`, and `vars`.
- [ ] Confirm there is no raw cron contract; any raw cron claim is a fail unless new requirements provide code evidence.
- [ ] Confirm schedule behavior in `backend/tests/test_workflow_package_runtime_api.py`, `backend/tests/test_workflow_package_run_contracts.py`, `backend/tests/test_runtime_repositories.py`, and `frontend/e2e/scheduled-tasks.spec.ts`.

## Model Connections/Secrets

- [ ] Confirm `backend/app/api/model_connections.py` exposes CRUD, connection-test, and capability-probe routes as platform-core APIs.
- [ ] Confirm `backend/app/models/model_connection.py::ModelConnection.secret_payload` uses `EncryptedJSONB` and public models never echo raw `apiKey`.
- [ ] Confirm `backend/app/schemas/model_connection.py` allows public writes to `protocolProfile` but rejects public capability/policy authorship except through backend-owned probe/test flows.
- [ ] Confirm `backend/app/services/model_connection_service.py` preserves or updates stored secrets only through explicit write paths and masks secrets in reads/errors.
- [ ] Confirm package secret bindings use `backend/app/models/workflow_package.py::WorkflowPackageSecretBinding.secret_payload` with `EncryptedJSONB` and `backend/app/schemas/workflow_package.py::WorkflowPackageSecretBindingRead` without raw values.

## Tools/Runtime Tool Dispatch

- [ ] Confirm `/api/tools` in `backend/app/api/tools.py::list_tools` returns only `key`, `displayName`, and `description`.
- [ ] Historical audit note: earlier baselines expected platform-core direct memory tool entries. Current live docs require declarative Workflow Package `spec.memory` middleware instead, so confirm `/api/tools` does not expose direct memory runtime grants and extension-owned tools remain filtered by enabled extension state.
- [ ] Confirm extension-owned server-declared tools are filtered through `enabled_server_declared_tool_registry` and `ExtensionService.get_tool_catalog`.
- [ ] Confirm `backend/app/agents/runtime_tools/registry.py::RuntimeToolRegistry.dispatch` enforces enabled-extension state and granted tool keys before executor dispatch.
- [ ] Confirm runtime and catalog coverage in `backend/tests/test_runtime_tools.py`, `backend/tests/test_tool_catalog_api.py`, and `backend/tests/test_workflow_package_preflight.py`.

## Memory

- [ ] Confirm `backend/app/api/memory.py` exposes platform-core memory through POST routes requiring access-context payloads, not public global CRUD.
- [ ] Confirm `backend/app/schemas/memory.py` requires package context, concrete private scope, opaque `memoryId`, and grant-aware access models.
- [ ] Confirm `backend/app/services/memory_service.py` keeps canonical memory separate from report-domain history.
- [ ] Confirm workflow memory lives as declarative middleware and `/api/memory` review infrastructure, not as direct runtime tool grants or Finance report tooling.
- [ ] Confirm memory coverage in `backend/tests/test_memory_service.py`, `backend/tests/test_memory_domain_schemas.py`, `backend/tests/test_memory_layer_static_contracts.py`, `frontend/src/pages/memory/list.test.tsx`, and `frontend/e2e/memory.spec.ts`.

## Extensions

- [ ] Confirm `backend/app/extensions/registry.py::get_bundled_extension_registry` defines only `signaldeck.finance` and `signaldeck.digital_oracle` as statically resident bundled extensions.
- [ ] Confirm Finance loaders include API routers, server-declared tools, runtime tools, execution provider bundle, lifecycle hooks, dependency surfaces, and package-private MCP tool ownership.
- [ ] Confirm Digital Oracle loaders include only server-declared and runtime tools.
- [ ] Confirm `backend/app/services/extension_service.py::ExtensionService._to_read_model` exposes only `key`, `label`, and `enabled`.
- [ ] Confirm extension API and lifecycle tests cover slim public state, toggle behavior, default-enabled state, and enabled-state filtering.

## Finance Extension

- [ ] Confirm `backend/app/extensions/signaldeck_finance/api_routers.py` owns preserved finance `/api/v1` route registrations and extension gates.
- [ ] Confirm finance routes cover portfolios, balances, positions, trading operations, market data, templates, and reports, and are absent/blocked when `signaldeck.finance` is disabled.
- [ ] Confirm finance runtime tools and server-declared tool specs stay under `backend/app/extensions/signaldeck_finance/` and are not migrated into generic platform runtime modules without an explicit shared contract.
- [ ] Confirm historical agent-memory report readers and `signaldeck.finance.reports.lookup` stay finance/report-owned, while canonical memory remains platform-core.
- [ ] Confirm frontend Finance route/nav contributions come from `frontend/src/extensions/signaldeck-finance/scaffold.ts` and are gated by `frontend/src/extensions/runtime-helpers.ts`.

## Frontend Routing/Navigation

- [ ] Confirm `frontend/src/routes.ts` registers Finance Workspace routes through `assembleFinanceWorkspaceRoutes()` plus platform routes for extensions, workflow packages, model connections, memory, scheduled tasks, and runs.
- [ ] Confirm `frontend/src/routes.metadata.ts` classifies route ownership as platform, system, extension, or unknown and keeps sidebar metadata aligned with registered routes.
- [ ] Confirm `frontend/src/extensions/runtime-helpers.ts` filters extension-owned nav/routes/tools through backend extension state.
- [ ] Confirm `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts` has empty `navContributions` and `routeContributions` and only Digital Oracle tool-prefix discovery.
- [ ] Confirm `frontend/src/routes.test.tsx` sends removed routes to `NotFoundPage`, keeps `/workflow-packages/:packageId/run` separate from the editor, and proves no `/api/*` browser routes exist.
- [ ] Confirm browser coverage exists in `frontend/e2e/navigation.spec.ts`, `frontend/e2e/extensions.spec.ts`, `frontend/e2e/workflow-packages.spec.ts`, `frontend/e2e/scheduled-tasks.spec.ts`, `frontend/e2e/runs.spec.ts`, `frontend/e2e/memory.spec.ts`, and `frontend/e2e/model-connections.spec.ts`.

## API Conventions/Errors

- [ ] Confirm all response/request schemas inherit or compose through `backend/app/schemas/common.py::CamelModel` for camelCase aliases, forbidden extras, string decimal serialization, and UTC `Z` timestamps.
- [ ] Confirm `backend/app/main.py::api_error_handler` returns `{code, message, details[]}` and `request_validation_handler` returns the shared validation envelope.
- [ ] Confirm routes raise `ApiError` helpers from `backend/app/core/errors.py` rather than raw framework exceptions for domain failures.
- [ ] Confirm frontend API parsing uses shared API client/error helpers such as `frontend/src/lib/api-client.ts::ApiRequestError`.
- [ ] Confirm error-envelope tests in `backend/tests/test_api.py` preserve browser-safe public scalars and drop unsafe details.

## Persistence/Schema/Migrations

- [ ] Confirm `backend/app/db/session.py` and `backend/app/db/upgrades.py` are the live PostgreSQL initialization and repair authorities.
- [ ] Confirm run queue persistence includes `runs.status`, `queued_at`, `lease_owner`, `lease_expires_at`, `heartbeat_at`, `schedule_provenance`, package snapshot relationships, and claim indexes in `backend/app/models/run.py` and upgrade tests.
- [ ] Confirm schedule persistence includes `workflow_package_schedules` and `workflow_package_schedule_fires` with structured recurrence, fire status, schedule deletion behavior, and run provenance in `backend/app/models/workflow_package_schedule.py`.
- [ ] Confirm model-connection and package secret persistence uses encrypted JSONB columns in `backend/app/models/model_connection.py` and `backend/app/models/workflow_package.py`.
- [ ] Confirm no Alembic scaffold, cache directory, generated build output, or historical docs are treated as schema authority.

## Tests And CI

- [ ] Confirm `docs/requirements/traceability-matrix.md` maps each confirmed FR to code and test evidence before adding or deleting checklist items.
- [ ] Confirm backend quality gates in `.github/workflows/ci.yml` run `uv run ruff check app tests`, `black --check`, `isort --check-only`, `mypy app`, and `pytest` after `uv sync --frozen`.
- [ ] Confirm frontend quality gates in `.github/workflows/ci.yml` run `pnpm lint`, `pnpm typecheck`, `pnpm build`, and `pnpm test:run` after `pnpm install --frozen-lockfile`.
- [ ] Confirm frontend E2E in `.github/workflows/ci.yml` depends on version sync, backend quality, and frontend quality, installs Chromium, and runs `pnpm test:e2e`.
- [ ] Confirm version-sync checks `backend/VERSION` against `backend/pyproject.toml` and `frontend/VERSION` against `frontend/package.json`.
- [ ] If a requirement cannot be linked to a route, service, model, frontend path, or test, mark it `needs code evidence` and do not preserve unsupported legacy behavior.
