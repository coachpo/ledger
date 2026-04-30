# BACKEND MODELS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers SQLAlchemy model rules.

## OVERVIEW
`app/models/` defines SQLAlchemy ORM entities, table names, constraints, indexes, cache tables, and relationships for the preserved product data model plus the current agent-platform tables. Models stay persistence-focused and should not contain service-layer business rules.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Base mixins / metadata | `base.py` | declarative base, id/timestamp mixins |
| Portfolio entity | `portfolio.py` | unique slug, summary relationships |
| Balance entity | `balance.py` | balance rows scoped to portfolio, including `operation_type` |
| Position entity | `position.py` | aggregate positions scoped to portfolio |
| Trading operation entity | `trading_operation.py` | append-only operations and historical attribution metadata |
| Market quote entity | `market_quote.py` | quote cache rows keyed by provider, symbol, and as-of |
| Symbol-name cache | `symbol_name_cache.py` | unlogged cache table keyed by symbol |
| Text templates | `text_template.py` | stored template names and content |
| Reports | `report.py` | slug-addressed markdown snapshots with source and metadata |
| Platform config entities | `skill.py`, `mcp_server.py`, `model_connection.py`, `output_schema.py` | versioned capabilities, MCP servers, saved model connections, and output schemas; `skill.py` keeps the deferred physical table name |
| Platform execution entities | `agent.py`, `workflow.py`, `run.py` | versioned agents and workflows plus persisted run detail |
## CONVENTIONS
- ORM models use `Mapped[...]` annotations and `mapped_column(...)`.
- Use explicit table names via `__tablename__` and explicit indexes or `CheckConstraint`s.
- Relationships use `relationship()` only when the code actually needs them.
- Models should be persistence-oriented: columns, constraints, defaults, and relationships only.
- Unique constraints enforce business rules such as unique portfolio slugs, balance labels per portfolio, template names, versioned platform keys, and quote-cache lookup keys.
- Use mixins from `base.py` instead of repeating `id`, `created_at`, or `updated_at` columns.

## ANTI-PATTERNS
- Do not put business logic or validation methods on ORM models.
- Do not hide implicit defaults or rely on database-side behavior without matching app expectations.
- Do not omit indexes for frequently queried lookup paths.
- Do not create relationships just for convenience when ids suffice.
- Do not rename tables or columns casually; tests and upgrade helpers depend on them.
- Do not rename deferred capability storage names in docs as if implementation already changed. The physical `skills` table and related stored keys remain intentional compatibility details until a later migration.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_models.py
```

## NOTES
- `app/models/__init__.py` imports the full preserved-product and agent-platform model surface for startup registration.
- `model_connection.py` stores UI-managed provider endpoint defaults, encrypted API-key payload metadata, status, and last connection-test results.
- `run.py` persists workflow version identity, per-step outputs, final output, and run totals used by the run monitor.
- `report.py` stores unique `name` and `slug`, tracks `source` (`compiled` vs `uploaded`), and keeps optional metadata in JSONB under the `metadata` column.
- `symbol_name_cache.py` is intentionally `UNLOGGED` because the cache is reconstructible from provider lookups.
