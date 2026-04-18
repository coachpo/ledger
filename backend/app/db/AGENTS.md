# BACKEND DB GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `app/db/`.

## OVERVIEW
`app/db/` owns engine/session creation, PostgreSQL-only database initialization, cache resets for tests, numeric-id guardrails, in-code legacy-schema cleanup, and runtime seed bootstrap during startup. The package is split by responsibility across `engine.py`, `validation.py`, `upgrades.py`, and a thin `session.py` composition layer.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Engine/session factories | `engine.py` | cached `get_engine()` and `get_session_factory()` |
| Request-scoped sessions | `engine.py` | `get_db_session()` generator used by API dependencies |
| App startup DB init | `session.py` | `init_db()` composes model import, validation, upgrades, and runtime seed bootstrap |
| Engine / id validation | `validation.py` | PostgreSQL requirement and numeric-id guardrails |
| Schema upgrades | `upgrades.py` | portfolio slug backfill, balance op-type, report slug/source/metadata, market-quote name, `trading_operations.simulation_id`, obsolete-table cleanup |
| Seed bootstrap | `session.py`, `../services/runtime_seed_bootstrap.py` | startup mirror sync for seeded runtime catalog rows |
| Test cache resets | `engine.py` | `reset_db_caches()` for isolated test databases |

## CONVENTIONS
- `get_engine()` and `get_session_factory()` are cached; tests must clear them when swapping `DATABASE_URL`.
- `init_db()` is the only startup path: import models, `create_all()`, run upgrade helpers, then bootstrap runtime seed mirrors.
- `init_db()` owns startup database validation, table creation, and compatibility upgrades for preserved runtime data.
- The backend requires PostgreSQL via `postgresql+psycopg`; unsupported engines should fail fast during `init_db()`.
- Legacy UUID-backed portfolio tables are rejected before startup; this codebase only supports numeric ids.
- Upgrade helpers live in code, so raw SQL must stay valid for PostgreSQL.

## ANTI-PATTERNS
- Do not assume Alembic exists or add migration-only instructions here.
- Do not mutate schema from routes, services, or tests when `app/db/` is the upgrade authority.
- Do not reintroduce engine-specific fallback branches or non-PostgreSQL connection handling.
- Do not forget to clear engine/session caches in tests that monkeypatch `DATABASE_URL`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_db_upgrades.py tests/test_runtime_seed_bootstrap.py
```

## NOTES
- `upgrades.py` backfills missing portfolio slugs, adds `balances.operation_type`, upgrades `reports` with `slug`/`source`/`metadata`, adds `market_quotes.name`, upgrades `trading_operations.simulation_id`, and drops obsolete stock-analysis tables left by older builds.
- `session.py` imports the full model package, validates the engine and numeric-id schema, creates tables, runs legacy upgrades, and calls `bootstrap_runtime_seed_mirrors(session)` before commit.
- `create_app(init_database=False)` lets tests control initialization explicitly through fixtures.
