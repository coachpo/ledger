# BACKEND REPOSITORIES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers the data access layer.

## OVERVIEW
`app/repositories/` owns database queries: CRUD operations, filtering, aggregate lookups, quote-cache access, symbol-name cache access, stored-template lookup, orchestration lookup, and backtest cleanup/query helpers. Repositories abstract SQLAlchemy queries from services.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio queries | `portfolio.py` | list, get, slug lookup, aggregate counts |
| Balance queries | `balance.py` | list_for_portfolio, get_for_portfolio, get_by_label, add, delete |
| Position queries | `position.py` | list_for_portfolio, get_for_portfolio, get_by_symbol, add, delete |
| Trading operation queries | `trading_operation.py` | list_for_portfolio, list/delete for backtest attribution, add |
| Backtest queries | `backtest.py` | newest-first list plus interrupted-run lookup |
| Market quote cache queries | `market_quote.py` | get_latest, get_by_provider_symbol_as_of, add |
| Symbol-name cache queries | `symbol_name_cache.py` | symbol lookup plus `insert_if_missing()` |
| Orchestration role queries | `orchestration_role.py` | list_all, get_by_key, get_by_name |
| Orchestration character queries | `orchestration_character.py` | list_all, get_by_handle, enabled catalog query |
| Text-template queries | `text_template.py` | list_all, get_by_name |
| Report queries | `report.py` | newest-first listing, slug lookup, name lookup, backtest-tag cleanup |

## CONVENTIONS
- Each repository is constructed with a `Session` and exposes query methods.
- Methods return ORM objects, not Pydantic schemas; services handle conversion.
- Most repositories use `BaseRepository`; `MarketQuoteRepository` stays custom because its access patterns are narrower.
- Queries use SQLAlchemy `select()` plus `session.scalar()` / `session.scalars()` patterns.
- Aggregations use `func.count()` where services need counts or summaries.
- Repositories do not commit; services own transaction boundaries.
- Filtering uses SQLAlchemy `where()` clauses rather than ad-hoc Python filtering.

## ANTI-PATTERNS
- Do not commit from repositories; services own `commit()/rollback()`.
- Do not return Pydantic schemas; return ORM objects.
- Do not bypass repositories in services when an existing repository method fits.
- Do not use raw SQL unless SQLAlchemy cannot express the query cleanly.
- Do not change cache, orchestration, or template lookup semantics without updating the service and test layers together.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_backtests_api.py tests/test_orchestration_api.py
```

## NOTES
- Repositories are instantiated directly inside service constructors with the shared `Session`.
- `ReportRepository` keeps slug/name lookups simple, exposes metadata-based filters, and leaves name-generation policy to `ReportService`.
- `BacktestRepository.list_all()` eager-loads `portfolio` for list rendering and orders by `created_at DESC, id DESC`; `list_interrupted()` powers startup repair.
- `SymbolNameCacheRepository.insert_if_missing()` relies on PostgreSQL `ON CONFLICT DO NOTHING`, so repo behavior here is intentionally PostgreSQL-specific.
- `TradingOperationRepository` and `ReportRepository` both expose backtest-specific cleanup helpers so terminal deletes stay query-driven instead of scanning in service code.
- `MarketQuoteRepository` stores cache entries keyed by `(provider, symbol, as_of)` and lets services decide whether to reuse or insert.
- `OrchestrationRoleRepository` and `OrchestrationCharacterRepository` keep lookup/catalog queries narrow, leaving version checks and business rules to `OrchestrationService`.
