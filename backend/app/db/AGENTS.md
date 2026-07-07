# BACKEND DB GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers `app/db/`.

## OVERVIEW
`app/db/` owns engine/session creation, PostgreSQL-only database initialization, cache resets for tests, numeric-id guardrails, bundled Workflow Package seeding, and startup stale-run recovery. There is no live migration framework; schema changes require a database reset until data must survive upgrades.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Engine/session factories | `engine.py` | cached `get_engine()` and `get_session_factory()` |
| Request-scoped sessions | `engine.py` | `get_db_session()` generator used by API dependencies |
| App startup DB init | `session.py` | `init_db()` composes model import, validation, table creation, bundled package seeding, and startup recovery |
| Engine / id validation | `validation.py` | PostgreSQL requirement and numeric-id guardrails |
| Bundled package seed | `seed.py`, `*.sql` | idempotent insertion/update of shipped Workflow Package presets |
| Startup recovery | `startup_recovery.py` | marks in-flight runs and child runtime rows failed/skipped after process restart |
| Test cache resets | `engine.py` | `reset_db_caches()` for isolated test databases |

## CONVENTIONS
- `get_engine()` and `get_session_factory()` are cached; tests must clear them when swapping `DATABASE_URL`.
- `init_db()` is the only startup path: import models, `create_all()`, seed bundled packages, and recover in-flight runs.
- `init_db()` owns startup database validation, table creation, bundled package seeding, and stale-run recovery.
- The backend requires PostgreSQL via `postgresql+psycopg`; unsupported engines should fail fast during `init_db()`.
- Legacy UUID-backed portfolio tables are rejected before startup; this codebase only supports numeric ids.
- Seed and recovery helpers live in code, so raw SQL must stay valid for PostgreSQL.
- Treat `startup_recovery.py` as authoritative for startup recovery behavior; if stale-run recovery changes, update the code path and its regression tests together.
- Do not add backfill, repair, cleanup, or compatibility paths for removed surfaces.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not assume Alembic exists or add migration-only instructions here.
- Do not mutate schema from routes, services, or tests; schema shape is model-owned and initialized by `create_all()`.
- Do not reintroduce engine-specific fallback branches or non-PostgreSQL connection handling.
- Do not forget to clear engine/session caches in tests that monkeypatch `DATABASE_URL`.
- Do not create alternate startup seed or recovery paths outside `init_db()`, `seed.py`, and `startup_recovery.py`.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_db_bootstrap.py
```

## NOTES
- `seed.py` loads bundled Workflow Package SQL presets idempotently.
- `startup_recovery.py` recovers stale agent-platform runs.
- `session.py` imports the full model package, validates the engine and numeric-id schema, creates tables, seeds bundled packages, and runs startup recovery.
- `create_app(init_database=False)` lets tests control initialization explicitly through fixtures.
