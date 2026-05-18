# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for SignalDeck. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error/telemetry helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py`, and executable agent workflows are accepted only through Workflow Package APIs. The live request path includes the bundled `signaldeck.finance` Finance Workspace extension plus platform routes for Workflow Packages, Model Connections, Extensions, Tools, and Runs.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

Future backend upgrade work must keep generic platform behavior separate from extension-owned behavior. Promote finance-owned routes, providers, runtime tools, or hooks into core layers only when a shared contract is intentional and the registries, docs, and tests move with it.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, telemetry, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation, extension-gated `/api/v1`, and dependency wiring
- `app/extensions/AGENTS.md` — bundled extension registry, slim state, private registrar, and ownership boundaries
- `app/extensions/signaldeck_finance/AGENTS.md` — `signaldeck.finance` route/tool/provider/report-memory ownership
- `app/agents/AGENTS.md` — tool catalog, native runtime tools, MCP security/runtime boundaries
- `app/services/AGENTS.md` — service orchestration, extension state, manifests, runtime execution, memory reports, quote-provider wiring
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
├── app/extensions/             # bundled extension registry and signaldeck.finance private registrar ownership
├── app/agents/                 # server-declared tools, native runtime tools, MCP boundaries
├── app/services/               # CRUD, extension state, manifests, execution, memory, templates, market data, trading rules
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
| Extension registry/state | `app/extensions/AGENTS.md`, `app/services/extension_service.py`, `app/api/extensions.py` | private bundled extension registry, slim `/api/extensions`, enabled tool/runtime filtering |
| Platform route families | `app/api/workflow_packages.py`, `app/api/model_connections.py`, `app/api/extensions.py`, `app/api/tools.py`, `app/api/runs.py` | Workflow Packages, Model Connections, Extensions, Tools, and Runs |
| Runtime tools / MCP / traces | `app/agents/AGENTS.md`, `app/services/agent_execution_service.py`, `app/services/run_service.py`, `app/core/telemetry.py` | server-declared tools, native runtime dispatch, MCP snapshots, Logfire trace ids/spans, memory writes |
| Preserved v1 route families | `app/extensions/signaldeck_finance/api_routers.py`, `app/api/portfolios.py`, `app/api/balances.py`, `app/api/positions.py`, `app/api/trading_operations.py`, `app/api/market_data.py`, `app/api/templates.py`, `app/api/reports.py` | preserved finance routes registered behind `signaldeck.finance` gates |
| Shared config / errors / telemetry / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, Logfire setup, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades |
| Service internals | `app/services/AGENTS.md` | transactions, manifest parser/compiler/decompiler/backfills, runtime execution, memory reports, market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, manifest contracts, memory metadata, serialization, camelCase aliasing |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache/model-connection tables, manifest fields, and runtime data access |
| Core test coverage | `tests/AGENTS.md` | CRUD, manifests, MCP, memory reports, runtime tools, preserved legacy coverage, and DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids where applicable, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, finance-scoped service factories imported from `app.extensions.signaldeck_finance.dependencies`, `ExtensionService`, `ToolCatalog`, MCP connection testing, platform services, `RunService`, and quote providers.
- `app/extensions/registry.py` declares bundled extension identity, initial enabled seeding, and private registrar paths; `ExtensionService` resolves persisted/default state and supplies enabled ToolCatalog/runtime registries.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Logfire setup and trace/span id formatting live in `app/core/telemetry.py`; run execution must keep working when no Logfire token is configured.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics; agent-memory report updates route through memory services.
- Workflow package writes use YAML manifest parser/compiler/decompiler services; legacy `spec.skills`, YAML aliases/anchors/merge keys, unsupported tags, non-finite values, duplicate refs, raw global ids, and old workflow roots stay invalid.
- Legacy orchestration, Studio, Tryout, runtime-v2 routes, and retired global authoring routes are not mounted live. Keep docs aligned with Workflow Packages, Model Connections, Extensions, Tools, and Runs; legacy/unmounted modules are cutover context only.
- `signaldeck.finance` owns preserved `/api/v1` finance routers, finance service dependencies, provider factories, finance runtime tools, and report-backed memory hooks while enabled.
- Tools are global read-only metadata at `/api/tools`; packages reference tool keys through package-local capability profiles. Current finance-owned native tools cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, report lookup, and report memory writes. Keep runtime tool keys and OpenAI function names unchanged.
- LLM-provider calls must stay inside official SDK clients (`OpenAI`) rather than ad-hoc raw HTTP request code.

## ANTI-PATTERNS
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
- Do not bypass `ExtensionService`, extension gates, or private registrars to expose finance routes/tools/providers directly.
- Do not add plugin-manifest metadata to public extension schemas, OpenAPI, run payloads, or docs. `/api/extensions` stays limited to `key`, `label`, and `enabled`.
- Do not migrate finance-owned behavior into generic core services or backend docs without first defining the shared platform contract and updating ownership/tests together.
- Do not reintroduce retired orchestration, Studio, Tryout, or runtime-v2 surfaces as live backend docs or routes.
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
- `tests/test_api.py` is the high-signal regression file for CRUD, templates, reports, trading operations, market-data fallback, symbol-name cache behavior, report placeholder cycles, and legacy-schema upgrades.
- Extension API, extension registry, lifecycle matrix, social sentiment, manifest, MCP, runtime-tool, memory-report, workflow package, tool catalog, model connection, and reset-seed tests cover the current agent-platform and finance-extension contract beyond the original runtime suite.
- `tests/test_workflow_package_*.py`, `tests/test_workflow_package_runtime_api.py`, `tests/test_workflow_package_runtime_artifacts.py`, `tests/test_workflow_package_run_contracts.py`, `tests/test_memory_domain_schemas.py`, `tests/test_runtime_models.py`, and `tests/test_runtime_repositories.py` cover current execution, saved model connections, trace, run-owned snapshot provenance, memory DTOs, and current-package persistence contracts.
- `tests/test_runtime_db_upgrades.py` and `tests/test_legacy_backend_cutover.py` cover startup schema repair, retired-table cleanup, and removed-route guarantees after cutover.
- There is no live Alembic migration path; schema changes stay in `app/db/upgrades.py`, even if a scaffold reappears.
