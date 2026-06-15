# BACKEND REPOSITORIES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers the data access layer.

## OVERVIEW
`app/repositories/` owns database queries: CRUD operations, filtering, aggregate lookups, quote-cache access, symbol-name cache access, stored-template and report lookup, and the current agent-platform config and run persistence reads. Repositories abstract SQLAlchemy queries from services.

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
| Portfolio queries | `portfolio.py` | list, get, slug lookup, aggregate counts |
| Balance queries | `balance.py` | list_for_portfolio, get_for_portfolio, get_by_label, add, delete |
| Position queries | `position.py` | list_for_portfolio, get_for_portfolio, get_by_symbol, add, delete |
| Trading operation queries | `trading_operation.py` | list_for_portfolio, historical attribution helpers, add |
| Market quote cache queries | `market_quote.py` | get_latest, get_by_provider_symbol_as_of, add |
| Symbol-name cache queries | `symbol_name_cache.py` | symbol lookup plus `insert_if_missing()` |
| Text-template queries | `text_template.py` | list_all, get_by_name |
| Report queries | `report.py` | newest-first listing, slug lookup, and name lookup |
| Platform package queries | `workflow_package.py`, `workflow_package_schedule.py` | current package reads/writes, import/export, preflight, schedules, due-fire claims, fire history, and lifecycle helpers |
| Platform global queries | `model_connection.py`, `run.py` | saved model connection lookup, package run provenance, schedule-linked runs, and run list/detail helpers |
| Quarantined legacy repositories | `agent.py`, `workflow.py`, `capability.py`, `mcp_server.py`, `output_schema.py` | cutover-era data access kept out of live route/service wiring; do not use for new package-first behavior |
## CONVENTIONS
- Each repository is constructed with a `Session` and exposes query methods.
- Methods return ORM objects, not Pydantic schemas; services handle conversion.
- Most repositories use `BaseRepository`; narrow repositories stay custom when their access patterns are specialized.
- Queries use SQLAlchemy `select()` plus `session.scalar()` / `session.scalars()` patterns.
- Aggregations use `func.count()` where services need counts or summaries.
- Repositories do not commit; services own transaction boundaries.
- Filtering uses SQLAlchemy `where()` clauses rather than ad-hoc Python filtering.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not commit from repositories; services own `commit()/rollback()`.
- Do not return Pydantic schemas; return ORM objects.
- Do not bypass repositories in services when an existing repository method fits.
- Do not use raw SQL unless SQLAlchemy cannot express the query cleanly.
- Do not change cache, preserved product lookup semantics, or current agent-platform persistence behavior without updating the service and test layers together.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_repositories.py
```

## NOTES
- Repositories are instantiated directly inside service constructors with the shared `Session`.
- `ReportRepository` keeps slug and name lookups simple, exposes metadata-based filters, and leaves name-generation policy to `ReportService`.
- `WorkflowPackageRepository` keeps current package persistence and lookup behavior centralized.
- `WorkflowPackageScheduleRepository` and `WorkflowPackageScheduleFireRepository` own schedule list/detail filters, due-schedule locking, idempotent fire inserts, fire history, latest-run lookup, and active-run checks.
- `ModelConnectionRepository` filters saved provider connections by status for list/editor/package-binding flows.
- `RunRepository` backs current run list/detail surfaces, backend progress/queue projections, package-qualified queue claims, schedule-linked run lookups, and persisted package-run lookup behavior.
- `TradingOperationRepository` retains historical attribution helpers where preserved legacy columns still matter, but there is no active `SimulationRepository` in the shipped package.
- Legacy global-authoring repositories are quarantine/upgrade context only. New work should target Workflow Package, schedule, model-connection, memory, and run repositories.
