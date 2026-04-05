# BACKEND MODELS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers SQLAlchemy model rules.

## OVERVIEW
`app/models/` defines SQLAlchemy ORM entities, table names, constraints, indexes, cache tables, and relationships. Models stay persistence-focused and should not contain service-layer business rules.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Base mixins / metadata | `base.py` | declarative base, id/timestamp mixins |
| Portfolio entity | `portfolio.py` | unique slug, summary relationships |
| Balance entity | `balance.py` | balance rows scoped to portfolio, including `operation_type` |
| Position entity | `position.py` | aggregate positions scoped to portfolio |
| Trading operation entity | `trading_operation.py` | append-only simulated operations |
| Backtest entity | `backtest.py` | webhook config, callback status, progress, selected deposit balance, results JSONB |
| Market quote entity | `market_quote.py` | quote cache rows keyed by provider/symbol/as-of |
| Symbol-name cache | `symbol_name_cache.py` | unlogged cache table keyed by symbol |
| Text templates | `text_template.py` | stored template names and content |
| Reports | `report.py` | slug-addressed markdown snapshots with source + metadata |

## CONVENTIONS
- ORM models use `Mapped[...]` annotations and `mapped_column(...)`.
- Use explicit table names via `__tablename__` and explicit indexes or `CheckConstraint`s.
- Relationships use `relationship()` only when the code actually needs them.
- Models should be persistence-oriented: columns, constraints, defaults, and relationships only.
- Unique constraints enforce business rules such as unique portfolio slugs, balance labels per portfolio, template names, and quote-cache lookup keys.
- Use mixins from `base.py` instead of repeating `id`, `created_at`, or `updated_at` columns.

## ANTI-PATTERNS
- Do not put business logic or validation methods on ORM models.
- Do not hide implicit defaults or rely on database-side behavior without matching app expectations.
- Do not omit indexes for frequently queried lookup paths.
- Do not create relationships just for convenience when ids suffice.
- Do not rename tables or columns casually; tests and upgrade helpers depend on them.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_backtests_api.py
```

## NOTES
- `portfolio.py` keeps lightweight relationships for balances, positions, and trading operations so API summary counts stay easy to assemble.
- `balance.py` persists `operation_type` directly and the DB upgrade helper backfills legacy rows to `DEPOSIT`.
- `trading_operation.py` is append-only by design to preserve auditability of simulated actions.
- `backtest.py` keeps per-run webhook config, benchmark symbols, current-cycle fields, recent activity, results, and startup-repairable status fields on a single row linked back to `Portfolio`.
- `market_quote.py` stores cached quote payloads with `previous_close`, freshness metadata, provider-specific symbol keys, and optional issuer `name`.
- `report.py` stores unique `name` and `slug`, tracks `source` (`compiled` vs `uploaded`), and keeps optional metadata in JSONB under the `metadata` column.
- `symbol_name_cache.py` is intentionally `UNLOGGED` because the cache is reconstructible from provider lookups.
