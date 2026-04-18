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
| Trading operation entity | `trading_operation.py` | append-only operations and historical attribution metadata |
| Orchestration role entity | `orchestration_role.py` | stable role keys, names, system prompts, version counters |
| Orchestration character entity | `orchestration_character.py` | stable handles, role linkage, prompt-append text, version counters |
| Runtime run entity | `runtime_run.py` | caller identity, workflow linkage, execution status, final-output metadata |
| Runtime artifact entity | `runtime_run_artifact.py` | persisted runtime artifact payloads |
| Runtime approval entity | `runtime_approval.py` | approval gates and actor/reason state |
| Runtime trace entity | `runtime_trace_event.py` | trace event history for Studio and runtime inspection |
| Runtime checkpoint entity | `runtime_checkpoint.py` | resumable execution checkpoints |
| Studio catalog entities | `agent_spec.py`, `workflow_spec.py`, `capability_registry_entry.py`, `persona_profile.py`, `persona_projection_event.py` | managed and seeded catalog/state rows |
| Market quote entity | `market_quote.py` | quote cache rows keyed by provider/symbol/as-of |
| Symbol-name cache | `symbol_name_cache.py` | unlogged cache table keyed by symbol |
| Text templates | `text_template.py` | stored template names and content |
| Reports | `report.py` | slug-addressed markdown snapshots with source and metadata |

## CONVENTIONS
- ORM models use `Mapped[...]` annotations and `mapped_column(...)`.
- Use explicit table names via `__tablename__` and explicit indexes or `CheckConstraint`s.
- Relationships use `relationship()` only when the code actually needs them.
- Models should be persistence-oriented: columns, constraints, defaults, and relationships only.
- Unique constraints enforce business rules such as unique portfolio slugs, balance labels per portfolio, template names, orchestration keys/handles, runtime uniqueness, and quote-cache lookup keys.
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
uv run pytest tests/test_api.py tests/test_runtime_models.py tests/test_orchestration_api.py
```

## NOTES
- `portfolio.py` keeps lightweight relationships for balances, positions, and trading operations so API summary counts stay easy to assemble.
- `balance.py` persists `operation_type` directly and the DB upgrade helper backfills legacy rows to `DEPOSIT`.
- `trading_operation.py` is append-only by design to preserve auditability of stored actions.
- `runtime_run.py`, `runtime_run_artifact.py`, `runtime_approval.py`, `runtime_trace_event.py`, and `runtime_checkpoint.py` define the active execution persistence surface imported by `app/models/__init__.py`.
- `agent_spec.py`, `workflow_spec.py`, `capability_registry_entry.py`, `persona_profile.py`, and `persona_projection_event.py` back the Studio catalog and persona projection surfaces.
- `orchestration_role.py` stores stable keys, unique names, version counters, and a one-to-many role-to-character relationship.
- `orchestration_character.py` stores stable handles, display names, prompt append text, version counters, and a required role reference.
- `report.py` stores unique `name` and `slug`, tracks `source` (`compiled` vs `uploaded`), and keeps optional metadata in JSONB under the `metadata` column.
- `symbol_name_cache.py` is intentionally `UNLOGGED` because the cache is reconstructible from provider lookups.
