# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for SignalDeck. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error/telemetry helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py`, and executable agent workflows are accepted only through Workflow Package APIs. The live request path includes the statically resident `signaldeck.finance` Finance Workspace extension, the tool-only `signaldeck.digital_oracle` extension, and platform routes for Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Memory, Tools, and Runs.

Extension model: SignalDeck Core ships statically resident extensions in code, while backend state and gates decide which routes, tools, providers, and hooks are exposed.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative old paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or non-goal surfaces, not live acceptance paths.

Future backend upgrade work must keep generic platform behavior separate from extension-owned behavior. Promote extension-owned routes, providers, runtime tools, or hooks into core layers only when a shared contract is intentional and the registries, docs, and tests move with it.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, telemetry, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation, extension-gated `/api/v1`, and dependency wiring
- `app/extensions/AGENTS.md` — statically resident extension registry, slim state, private registrar, and ownership boundaries
- `app/extensions/signaldeck_finance/AGENTS.md` — `signaldeck.finance` route/tool/provider/report ownership
- `app/agents/AGENTS.md` — tool catalog, native runtime tools, MCP security/runtime boundaries, and platform memory-tool ownership
- `app/services/AGENTS.md` — service orchestration, extension state, manifests, Scheduled Tasks, execution providers/lifecycle hooks, runtime execution, core memory, historical agent-memory reports, and quote-provider wiring
- `app/schemas/AGENTS.md` — request/response validation, manifests, memory metadata, serialization
- `app/models/AGENTS.md` — ORM entities, constraints, indexes, cache tables, manifests, runtime metadata
- `app/repositories/AGENTS.md` — SQLAlchemy query/repository patterns and runtime lookups
- `tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and high-signal regression tests

## STRUCTURE
```text
backend/
├── app/core/                   # config, errors, formatting, telemetry, constants
├── app/db/                     # engine/session/init + PostgreSQL upgrade helpers
├── app/api/                    # APIRouter modules + dependency wiring for /api/v1 and /api/*
├── app/extensions/             # statically resident extension registry plus finance and Digital Oracle ownership
├── app/agents/                 # server-declared tools, native runtime tools, MCP boundaries
├── app/services/               # CRUD, extension state, manifests, schedules, execution, queueing, memory, templates, market data, trading rules
├── app/workers/                # long-lived scheduler worker entrypoints for queued package runs
├── app/repositories/           # persistence queries
├── app/models/                 # SQLAlchemy entities + constraints/indexes
├── app/schemas/                # CamelModel request/response contracts
└── tests/                      # pytest integration tests with isolated PostgreSQL databases
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| API route handlers | `app/api/AGENTS.md` | route handler rules, service delegation, error translation |
| Service construction | `app/api/dependencies.py` | constructs extension-aware CRUD, template, report, ToolCatalog, MCP tester, platform, run, and quote-provider services |
| Extension registry/state | `app/extensions/AGENTS.md`, `app/services/extension_service.py`, `app/api/extensions.py` | private statically resident extension registry, slim `/api/extensions`, enabled tool/runtime filtering |
| Platform route families | `app/api/workflow_packages.py`, `app/api/schedules.py`, `app/api/model_connections.py`, `app/api/extensions.py`, `app/api/memory.py`, `app/api/tools.py`, `app/api/runs.py` | Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Memory, Tools, and Runs |
| Runtime tools / MCP / scheduler / traces | `app/agents/AGENTS.md`, `app/workers/AGENTS.md`, `app/services/workflow_package_schedule_service.py`, `app/services/workflow_package_schedule_materializer.py`, `app/services/run_queue_service.py`, `app/services/run_read_projection.py`, `app/services/run_service.py`, `app/core/telemetry.py` | server-declared tools, due schedule materialization, extension-filtered native runtime dispatch, explicit queued-run worker, backend progress/queue read models, MCP snapshots, Logfire trace ids/spans, and memory writes |
| Preserved v1 route families | `app/extensions/signaldeck_finance/api_routers.py`, `app/api/portfolios.py`, `app/api/balances.py`, `app/api/positions.py`, `app/api/trading_operations.py`, `app/api/market_data.py`, `app/api/templates.py`, `app/api/reports.py` | preserved finance routes registered behind `signaldeck.finance` gates |
| Shared config / errors / telemetry / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, Logfire setup, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades, startup repair, and repair markers |
| Service internals | `app/services/AGENTS.md` | transactions, manifest parser/compiler/decompiler/backfills, schedule recurrence/materialization, execution providers/lifecycle hooks, runtime execution, queue claims/read projections, core memory, historical agent-memory reports, and market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, manifest contracts, run progress/queue read models, memory metadata, serialization, camelCase aliasing |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache/model-connection tables, manifest fields, run forks, and runtime data access |
| Core test coverage | `tests/AGENTS.md` | CRUD, manifests, MCP, package preflight, rerun/fork contracts, core memory and historical agent-memory reports, runtime tools, removed-surface coverage, and DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids where applicable, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, finance-scoped service factories imported from `app.extensions.signaldeck_finance.dependencies`, `ExtensionService`, `ToolCatalog`, MCP connection testing, platform services, `RunService`, and quote providers.
- `app/extensions/registry.py` declares statically resident extension identity, initial enabled seeding, and private registrar paths; `ExtensionService` resolves persisted/default state and supplies enabled ToolCatalog/runtime registries.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- `PORTFOLIO_CURRENCY` in `app/core/constants.py` is the current USD source for balances, positions, trading operations, template available balance, and quote currency checks; portfolio schemas do not expose `baseCurrency`/`base_currency`.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Logfire setup and trace/span id formatting live in `app/core/telemetry.py`; run execution must keep working when no Logfire token is configured.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics; agent-memory report updates route through memory services.
- Workflow package writes use YAML manifest parser/compiler/decompiler services; unsupported `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite values, duplicate refs, raw global ids, and old workflow roots stay invalid. Package save/import is artifact-only; launch, preflight, rerun, and fork evaluate live readiness later.
- Scheduled Tasks use `/api/schedules`, structured recurrence, IANA timezones, JSON input templates, idempotent manual fires, and ordinary queued runs. The scheduler worker materializes due fires; routes do not execute runs inline.
- Removed orchestration, Studio, Tryout, runtime-v2 routes, and global authoring routes are not mounted live. Keep docs aligned with Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Memory, Tools, and Runs.
- `signaldeck.finance` owns preserved `/api/v1` finance routers, finance service dependencies, provider factories, finance runtime tools, report lookup, and historical agent-memory report readers while enabled.
- `signaldeck.digital_oracle` is default enabled and tool-only in this upgrade. It owns `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup` with canonical owner-qualified tool keys and mechanical OpenAI function names, and it adds no API router, provider bundle, lifecycle hook, route, or nav surface.
- Tools are global read-only metadata at `/api/tools`; packages reference only canonical owner-qualified tool keys through package-local capability profiles. The live public keys are `signaldeck.core.memory.write`, `signaldeck.core.memory.lookup`, `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, `signaldeck.finance.positions.lookup`, `signaldeck.finance.reports.lookup`, `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`. Platform-core memory tools stay separate from extension-owned Finance Workspace and Digital Oracle tools.
- LLM-provider calls must stay inside official SDK clients (`OpenAI`) rather than ad-hoc raw HTTP request code.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
- Do not bypass `ExtensionService`, extension gates, or private registrars to expose finance routes/tools/providers directly.
- Do not add plugin-manifest metadata to public extension schemas, OpenAPI, run payloads, or docs. `/api/extensions` stays limited to `key`, `label`, and `enabled`.
- Do not migrate finance-owned behavior into generic core services or backend docs without first defining the shared platform contract and updating ownership/tests together.
- Do not reintroduce removed orchestration, Studio, Tryout, or runtime-v2 surfaces as live backend docs or routes.
- Do not add raw `httpx`/`requests` model-calling code in backend application paths when the provider offers an official library.

## COMMANDS
```bash
uv sync
uv run uvicorn app.main:app --reload
uv run pytest tests/test_api.py
```

## VALIDATION
```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## NOTES
- `tests/test_api.py` is the high-signal regression file for CRUD, templates, reports, trading operations, market-data fallback, symbol-name cache behavior, report placeholder cycles, and schema upgrades.
- Extension API, extension registry, lifecycle matrix, social sentiment, manifest, MCP, runtime-tool, memory-report, workflow package, schedule, tool catalog, model connection, and reset-seed tests cover the current agent-platform and finance-extension contract beyond the original runtime suite.
- `tests/test_workflow_package_*.py`, `tests/test_workflow_package_runtime_api.py`, `tests/test_workflow_package_runtime_artifacts.py`, `tests/test_workflow_package_run_contracts.py`, `tests/test_workflow_package_preflight.py`, `tests/test_workflow_run_contract_schemas.py`, `tests/test_run_operation_invocations.py`, `tests/test_memory_domain_schemas.py`, `tests/test_runtime_models.py`, and `tests/test_runtime_repositories.py` cover current execution, saved model connections, preflight/tool contracts, scheduled tasks, rerun/fork behavior, scheduler queues, trace, run-owned snapshot provenance, memory DTOs, and current-package persistence contracts.
- `tests/test_runtime_db_upgrades.py` and `tests/test_legacy_backend_cutover.py` cover startup schema repair, schedule tables, retired-table cleanup, and removed-route guarantees.
- There is no live Alembic migration path; schema changes stay in `app/db/upgrades.py`, even if a scaffold reappears.
