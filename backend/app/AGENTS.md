# BACKEND APP GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers the Python application package under `backend/app/`.

## OVERVIEW
`backend/app/` is the FastAPI application package: app factory, split route roots, dependency composition, extension registry wiring, services, repositories, models, schemas, PostgreSQL startup repair, runtime agents/tools/MCP, and worker entrypoints. Keep this layer package-first and extension-aware: Workflow Packages are the executable root, while Finance Workspace and Digital Oracle behavior stays owned by their bundled extensions unless a shared platform contract is explicit.

## CHILD DOCS
- `api/AGENTS.md` — APIRouter modules, dependency injection, route/service boundaries
- `core/AGENTS.md` — settings, errors, formatting, constants, telemetry
- `db/AGENTS.md` — engine/session lifecycle, bundled package seeding, startup recovery
- `extensions/AGENTS.md` — statically resident bundled extension registry and ownership
- `agents/AGENTS.md` — tool catalog, native runtime tools, MCP runtime boundaries
- `services/AGENTS.md` — business rules, transactions, runtime execution, schedules
- `repositories/AGENTS.md` — SQLAlchemy query and persistence helpers
- `models/AGENTS.md` — ORM entities, constraints, indexes, runtime metadata
- `schemas/AGENTS.md` — Pydantic request/response and manifest contracts
- `workers/AGENTS.md` — scheduler worker entrypoints and queue execution

## STRUCTURE
```text
app/
├── main.py          # create_app(), health/readiness, router mounting
├── api/             # route modules and request-scoped dependencies
├── core/            # shared backend primitives
├── db/              # PostgreSQL session/init, seed, and startup recovery code
├── extensions/      # bundled extension registry and extension packages
├── agents/          # server tools, runtime tools, MCP runtime
├── services/        # business and orchestration layer
├── repositories/    # persistence access helpers
├── models/          # SQLAlchemy models
├── schemas/         # Pydantic contracts
└── workers/         # scheduler process entrypoints
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| App bootstrap | `main.py` | `create_app()`, Logfire setup, health/readiness, `/api` and `/api/v1` mounting |
| Current platform APIs | `api/platform_router.py`, `api/{workflow_packages,schedules,model_connections,extensions,tools,runs}.py` | live package-first platform routes under `/api` |
| Preserved finance APIs | `api/router.py`, `extensions/signaldeck_finance/api_routers.py`, `api/{portfolios,balances,positions,trading_operations,market_data,templates,reports}.py` | extension-contributed `/api/v1` routes gated by `signaldeck.finance` |
| Dependency composition | `api/dependencies.py` | request-scoped sessions, extension service, ToolCatalog, provider bundles, run services |
| Extension state and registrars | `extensions/registry.py`, `services/extension_service.py` | statically resident extension identity plus enabled-route/tool/provider filtering |
| Runtime execution | `services/run_service.py`, `services/agent_execution_service.py`, `agents/runtime_tools/`, `agents/mcp/` | queued package execution, model calls, native tools, MCP dispatch, trace ids |
| Scheduler process | `workers/run_scheduler.py` | separate worker entrypoint; not FastAPI lifespan work |
| DB bootstrap | `db/session.py`, `db/seed.py`, `db/startup_recovery.py` | `create_all`, bundled package seeding, and stale-run recovery; no live Alembic path |

## CONVENTIONS
- `main.create_app()` includes `platform_router` under `/api` and extension-contributed `api_router` under `/api/v1`; keep the split deliberate.
- `api/dependencies.py` is the request composition root. Routes should not instantiate repositories, providers, ToolCatalogs, MCP clients, or run services ad hoc.
- Routers validate request shape and delegate. Services own business rules, readiness checks, transactions, provider orchestration, runtime execution, and rollback behavior.
- Repositories own SQLAlchemy query mechanics only. Models own persistence shape and constraints. Schemas own external camelCase contracts through `CamelModel`.
- Shared formatting, `ApiError`, settings, constants, and Logfire helpers belong in `core/`; do not duplicate them in routes or services.
- Extension-owned behavior enters through `extensions/registry.py` registrar loaders and `ExtensionService` enabled-state filtering. Finance and Digital Oracle tool keys stay owner-qualified.
- Workflow Package manifests, schedules, runs, and package-private MCP remain platform-core app contracts; global authoring surfaces stay removed.
- The scheduler worker calls `init_db()` and executes queued runs in a separate process. FastAPI startup should not claim runs or materialize schedules inline.
- Application LLM calls stay behind official SDK clients and gateway services, not raw HTTP helpers.

## ANTI-PATTERNS
- Do not add auth, RBAC, tenant/account ownership, login/session, or account-management app plumbing unless product scope changes.
- Do not bypass `ExtensionService`, registry loaders, or extension gates to expose routes, tools, or providers.
- Do not move Finance Workspace or Digital Oracle behavior into generic app services without an explicit shared-contract decision and coordinated tests/docs.
- Do not resurrect global agents, workflows, capabilities, standalone MCP servers, output schemas, skills, Studio, Tryout, orchestration, runtime-v2, or simulations routes.
- Do not treat Alembic scaffolds, docs, frontend output, or cache directories as backend app source of truth.
- Do not put business rules in route modules or persistence rules in schemas.
- Do not hand-build API envelopes or camelCase payloads; use `ApiError` and `CamelModel`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```
