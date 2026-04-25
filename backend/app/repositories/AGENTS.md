# BACKEND REPOSITORIES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers the data access layer.

## OVERVIEW
`app/repositories/` owns database queries: CRUD operations, filtering, aggregate lookups, quote-cache access, symbol-name cache access, stored-template and report lookup, and the current agent-platform config and run persistence reads. Repositories abstract SQLAlchemy queries from services.

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
| Platform config queries | `skill.py`, `mcp_server.py`, `model_connection.py`, `output_schema.py` | versioned catalog reads, saved model connections, and lifecycle lookups |
| Platform execution queries | `agent.py`, `workflow.py`, `run.py` | version pinning, workflow reads, and run list/detail helpers |
## CONVENTIONS
- Each repository is constructed with a `Session` and exposes query methods.
- Methods return ORM objects, not Pydantic schemas; services handle conversion.
- Most repositories use `BaseRepository`; narrow repositories stay custom when their access patterns are specialized.
- Queries use SQLAlchemy `select()` plus `session.scalar()` / `session.scalars()` patterns.
- Aggregations use `func.count()` where services need counts or summaries.
- Repositories do not commit; services own transaction boundaries.
- Filtering uses SQLAlchemy `where()` clauses rather than ad-hoc Python filtering.

## ANTI-PATTERNS
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
- `ModelConnectionRepository` filters saved provider connections by status for list/editor/agent-selection flows.
- `RunRepository` backs the current run list/detail surfaces and keeps persisted workflow-run lookup behavior centralized.
- `TradingOperationRepository` retains historical attribution helpers where preserved legacy columns still matter, but there is no active `SimulationRepository` in the shipped package.
