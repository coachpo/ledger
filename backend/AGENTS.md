# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for portfolio tracking. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py`, and the live request path now includes template compilation, report generation/upload/download, orchestration role and character management, plus `/api/v2` runtime, Studio, Tryout, and workflow-spec surfaces.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation and dependency wiring
- `app/services/AGENTS.md` — service orchestration, runtime execution, template compiler, quote-provider wiring, transaction ownership
- `app/schemas/AGENTS.md` — request/response validation, runtime payloads, and serialization
- `app/models/AGENTS.md` — ORM entities, constraints, indexes, cache tables, and runtime metadata
- `app/repositories/AGENTS.md` — SQLAlchemy query/repository patterns and runtime lookups
- `tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and high-signal regression tests

## STRUCTURE
```text
backend/
├── app/core/                   # config, errors, formatting, constants
├── app/db/                     # engine/session/init + PostgreSQL upgrade helpers
├── app/api/                    # APIRouter modules + dependency wiring for /api/v1 and /api/v2
├── app/services/               # CRUD, orchestration, runtime execution, Studio reads, Tryout flow, templates, market data, trading rules, provider protocol
├── app/repositories/           # persistence queries
├── app/models/                 # SQLAlchemy entities + constraints/indexes
├── app/schemas/                # CamelModel request/response contracts
└── tests/                      # pytest integration tests with isolated PostgreSQL databases
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| API route handlers | `app/api/AGENTS.md` | route handler rules, service delegation, error translation |
| Service construction | `app/api/dependencies.py` | constructs CRUD, template, report, orchestration, runtime, Studio, Tryout, workflow-spec, and quote-provider services |
| Orchestration management | `app/api/orchestration.py`, `app/services/orchestration_service.py`, `app/schemas/orchestration.py` | roles, characters, mention catalog, versioned updates, validation |
| Runtime workflow lifecycle | `app/api/runtime.py`, `app/api/workflow_specs.py`, `app/services/agent_runtime_service.py`, `app/services/workflow_spec_service.py` | public runtime runs, approvals, trace, and workflow catalog lifecycle |
| Studio reads | `app/api/studio.py`, `app/services/studio_query_service.py` | runs, artifacts, approvals, trace-event reads |
| Tryout flow | `app/api/tryouts.py`, `app/services/tryout_service.py`, `app/schemas/tryout.py` | execute, inspect, and persist Tryout runs |
| Runtime seed compatibility | `app/db/upgrades.py`, `app/services/runtime_seed_bootstrap.py`, `app/services/runtime_seed_catalog.py` | runtime seed cleanup, compatibility rewrites, and seeded mirror bootstrap |
| Shared config / errors / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades |
| Service internals | `app/services/AGENTS.md` | transactions, orchestration, runtime dispatch, template compiler, report workflows, symbol lookup cache, market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, serialization, camelCase aliasing, orchestration and runtime payloads |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache tables, orchestration models, runtime data access |
| Core test coverage | `tests/AGENTS.md` | CRUD, templates, reports, orchestration, runtime, Tryout, Studio, and DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids where applicable, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, CRUD services, `TemplateCompilerService`, `OrchestrationService`, `AgentRuntimeService`, `StudioQueryService`, `TryoutService`, `WorkflowSpecService`, and `YahooFinanceQuoteProvider`.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `OrchestrationService` owns versioned role/character CRUD, disabled-role checks, reserved-handle checks, and the mention catalog that merges seeded builtin targets with enabled characters.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics.
- `WorkflowSpecService`, `AgentRuntimeService`, `StudioQueryService`, and `TryoutService` define the live v2 execution and inspection path; keep docs aligned with those surfaces rather than removed simulation routes.
- LLM-provider calls must stay inside official SDK clients (`ChatOpenAI`, `OpenAI`) rather than ad-hoc raw HTTP request code.

## ANTI-PATTERNS
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
- Do not change orchestration role/character contracts, mention catalog behavior, or snapshot upgrade rules without updating orchestration tests and callers.
- Do not document `backend/app/api/simulations.py` or a simulation-first browser workflow as live backend surfaces; the shipped HTTP API is v1 CRUD plus v2 runtime/studio/tryout/spec routes.
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
- `tests/test_orchestration_api.py` covers role and character CRUD, duplicate/reserved/disabled validation, mention catalog behavior, and version bump expectations.
- `tests/test_runtime_api.py`, `tests/test_runtime_approvals_api.py`, `tests/test_runtime_artifacts.py`, and `tests/test_runtime_execution_adapters.py` cover the surviving runtime execution, approval, artifact, and frozen-adapter regressions.
- `tests/test_tryouts_api.py` and `tests/test_tryout_service.py` cover the public Tryout execute/read/persist flow and its service boundary.
- `tests/test_runtime_db_upgrades.py`, `tests/test_runtime_models.py`, and `tests/test_runtime_seed_bootstrap.py` cover retained runtime schema upgrade paths plus metadata/index expectations.
- `backend/alembic/` exists as scaffolding only; schema changes still live in `app/db/upgrades.py`.
