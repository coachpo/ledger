# BACKEND GUIDE

> Inherits root rules from `/AGENTS.md`. Local layer docs live under `app/*/AGENTS.md` and `tests/AGENTS.md`.

## OVERVIEW
FastAPI + SQLAlchemy + Pydantic backend for portfolio tracking. Routers stay thin, services own business rules and transaction boundaries, shared formatting/error helpers live in `app/core`, PostgreSQL initialization is composed in `app/db/session.py`, and the live request path now includes template compilation, report generation/upload/download, plus the current agent-platform routes for agents, skills, MCP servers, model connections, output schemas, workflows, and runs.

## CHILD DOCS
- `app/core/AGENTS.md` — settings, error envelope, normalization helpers
- `app/db/AGENTS.md` — engine/session lifecycle and PostgreSQL-only upgrade rules
- `app/api/AGENTS.md` — route-handler delegation and dependency wiring
- `app/services/AGENTS.md` — service orchestration, template compiler, quote-provider wiring, transaction ownership
- `app/schemas/AGENTS.md` — request/response validation and serialization
- `app/models/AGENTS.md` — ORM entities, constraints, indexes, cache tables, and runtime metadata
- `app/repositories/AGENTS.md` — SQLAlchemy query/repository patterns and lookups
- `tests/AGENTS.md` — pytest fixtures, isolated PostgreSQL databases, and high-signal regression tests

## STRUCTURE
```text
backend/
├── app/core/                   # config, errors, formatting, constants
├── app/db/                     # engine/session/init + PostgreSQL upgrade helpers
├── app/api/                    # APIRouter modules + dependency wiring for /api/v1 and /api/*
├── app/services/               # CRUD, agent-platform, templates, market data, trading rules, provider protocol
├── app/repositories/           # persistence queries
├── app/models/                 # SQLAlchemy entities + constraints/indexes
├── app/schemas/                # CamelModel request/response contracts
└── tests/                      # pytest integration tests with isolated PostgreSQL databases
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| API route handlers | `app/api/AGENTS.md` | route handler rules, service delegation, error translation |
| Service construction | `app/api/dependencies.py` | constructs CRUD, template, report, model-connection, agent-platform, and quote-provider services |
| Platform route families | `app/api/agents.py`, `app/api/skills.py`, `app/api/mcp_servers.py`, `app/api/model_connections.py`, `app/api/output_schemas.py`, `app/api/workflows.py`, `app/api/runs.py` | agents, skills, MCP servers, model connections, output schemas, workflows, and runs |
| Preserved v1 route families | `app/api/portfolios.py`, `app/api/balances.py`, `app/api/positions.py`, `app/api/trading_operations.py`, `app/api/market_data.py`, `app/api/templates.py`, `app/api/reports.py` | preserved portfolio, trading, market-data, template, and report routes |
| Shared config / errors / normalization | `app/core/AGENTS.md` | env aliases, `ApiError`, decimal/symbol/currency helpers |
| DB init/session | `app/db/AGENTS.md` | engine/session caches, `init_db()`, PostgreSQL upgrades |
| Service internals | `app/services/AGENTS.md` | transactions, template compiler, report workflows, model-connection tests, run execution, market-data fallback |
| API payload shape | `app/schemas/AGENTS.md` | Pydantic validation, serialization, camelCase aliasing |
| Persistence / constraints | `app/models/AGENTS.md`, `app/repositories/AGENTS.md` | ORM entities, report/cache/model-connection tables, and runtime data access |
| Core test coverage | `tests/AGENTS.md` | CRUD, templates, reports, preserved legacy coverage, and DB-upgrade coverage |

## CONVENTIONS
- Each route module declares `APIRouter(prefix=..., tags=[...])`, accepts integer ids where applicable, and delegates to a service.
- `app/api/dependencies.py` is the composition root for request-scoped `Session` objects, CRUD services, `TemplateCompilerService`, `ModelConnectionService`, the current platform services, and `YahooFinanceQuoteProvider`.
- Schemas inherit `CamelModel`; external JSON is camelCase, extra fields are forbidden, decimals serialize to strings, and datetimes serialize as UTC `Z` timestamps.
- Shared normalization and decimal parsing live in `app/core/formatting.py`; use `normalize_symbol`, `normalize_currency`, `parse_decimal_string`, `to_utc`, and `utcnow` instead of ad-hoc helpers.
- Shared domain errors come from `app/core/errors.py`; routes and services should raise `ApiError` helpers rather than raw framework exceptions.
- Services return read schemas via `*.model_validate(...)` and own `commit()/rollback()` around multi-step writes.
- `ReportService` owns slug normalization, timestamped report-name generation for compiled reports, external JSON creation, filtered list retrieval, markdown-upload validation, and download-by-slug semantics.
- Legacy orchestration, Studio, Tryout, and runtime-v2 routes are retired. Keep docs aligned with the current agent-platform routes for agents, skills, MCP servers, model connections, output schemas, workflows, and runs.
- LLM-provider calls must stay inside official SDK clients (`ChatOpenAI`, `OpenAI`) rather than ad-hoc raw HTTP request code.

## ANTI-PATTERNS
- Do not put business rules in routers or repositories.
- Do not raise raw `HTTPException` for domain errors; use `ApiError` helpers from `app/core/errors.py`.
- Do not hand-build camelCase payloads; let `CamelModel` serialize them.
- Do not skip normalization or decimal parsing on symbols, currencies, or numeric strings.
- Do not change template placeholder behavior, symbol lookup behavior, or CSV contracts without updating `tests/test_api.py` and the frontend callers.
- Do not change report compile/upload/download contracts, report filters, report placeholder behavior, or report slug rules without updating `tests/test_api.py` and the frontend callers.
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
- `tests/test_runtime_api.py`, `tests/test_runtime_artifacts.py`, `tests/test_runtime_models.py`, and `tests/test_runtime_repositories.py` cover the current agent-platform execution, saved model connections, trace, persistence, and version-pinning contracts.
- `tests/test_runtime_db_upgrades.py` and `tests/test_legacy_backend_cutover.py` cover startup schema repair, retired-table cleanup, and removed-route guarantees after cutover.
- `backend/alembic/` exists as scaffolding only; schema changes still live in `app/db/upgrades.py`.
