# BACKEND DB GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `app/db/`.

## OVERVIEW
`app/db/` owns engine/session creation, PostgreSQL-only database initialization, cache resets for tests, numeric-id guardrails, and in-code schema upgrades for preserved product tables, bundled extension state, and current agent-platform tables. `upgrades.py` is also the supported startup repair path for extension-state canonicalization, current-package/reference-table creation, run-fork tables, stale-run recovery, and retired-table cleanup.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Engine/session factories | `engine.py` | cached `get_engine()` and `get_session_factory()` |
| Request-scoped sessions | `engine.py` | `get_db_session()` generator used by API dependencies |
| App startup DB init | `session.py` | `init_db()` composes model import, validation, table creation, and upgrade helpers |
| Engine / id validation | `validation.py` | PostgreSQL requirement and numeric-id guardrails |
| Schema upgrades | `upgrades.py` | preserved-table backfills, `extension_states` repair/seeding, platform reference tables, `run_forks`, startup recovery, and legacy-table cleanup |
| Test cache resets | `engine.py` | `reset_db_caches()` for isolated test databases |

## CONVENTIONS
- `get_engine()` and `get_session_factory()` are cached; tests must clear them when swapping `DATABASE_URL`.
- `init_db()` is the only startup path: import models, `create_all()`, and run upgrade helpers.
- `init_db()` owns startup database validation, table creation, and compatibility upgrades for supported tables.
- The backend requires PostgreSQL via `postgresql+psycopg`; unsupported engines should fail fast during `init_db()`.
- Legacy UUID-backed portfolio tables are rejected before startup; this codebase only supports numeric ids.
- Upgrade helpers live in code, so raw SQL must stay valid for PostgreSQL.
- Treat `upgrades.py` as authoritative for startup cutover markers and recovery behavior; if schema repair or legacy normalization changes, update the code path and its regression tests together.

## ANTI-PATTERNS
- Do not assume Alembic exists or add migration-only instructions here.
- Do not mutate schema from routes, services, or tests when `app/db/` is the upgrade authority.
- Do not reintroduce engine-specific fallback branches or non-PostgreSQL connection handling.
- Do not forget to clear engine/session caches in tests that monkeypatch `DATABASE_URL`.
- Do not create alternate startup repair paths outside `init_db()` and `upgrades.py`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_db_upgrades.py tests/test_legacy_backend_cutover.py
```

## NOTES
- `upgrades.py` backfills missing portfolio slugs, adds `balances.operation_type`, upgrades `reports` with `slug`/`source`/`metadata`, adds `market_quotes.name`, repairs and seeds `extension_states`, creates current agent-platform/reference tables including `run_forks`, backfills placeholder model connections from legacy agent models, recovers stale agent-platform runs, and drops retired backend tables.
- `upgrades.py` also owns the package-startup cutover marker table used to avoid re-running one-way artifact migrations.
- `session.py` imports the full model package, validates the engine and numeric-id schema, creates tables, and runs upgrade helpers.
- `create_app(init_database=False)` lets tests control initialization explicitly through fixtures.
