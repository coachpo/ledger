# BACKEND MODELS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers SQLAlchemy model rules.

## OVERVIEW
`app/models/` defines SQLAlchemy ORM entities, table names, constraints, indexes, cache tables, and relationships for the preserved product data model, statically resident extension state, and current agent-platform tables. Models stay persistence-focused and should not contain service-layer business rules.

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
| Base mixins / metadata | `base.py` | declarative base, id/timestamp mixins |
| Portfolio entity | `portfolio.py` | unique slug, summary relationships |
| Balance entity | `balance.py` | balance rows scoped to portfolio, including `operation_type` |
| Position entity | `position.py` | aggregate positions scoped to portfolio |
| Trading operation entity | `trading_operation.py` | append-only operations and historical attribution metadata |
| Market quote entity | `market_quote.py` | quote cache rows keyed by provider, symbol, and as-of |
| Symbol-name cache | `symbol_name_cache.py` | unlogged cache table keyed by symbol |
| Text templates | `text_template.py` | stored template names and content |
| Reports | `report.py` | slug-addressed markdown snapshots with source and metadata |
| Extension state | `extension.py` | persisted enable/disable state for statically resident extension keys |
| Platform package entities | `workflow_package.py`, `workflow_package_schedule.py` | package artifacts, package-backed schedules, and schedule fire history |
| Platform global entities | `model_connection.py`, `run.py` | saved model connections, persisted global run detail, schedule provenance, package provenance |
## CONVENTIONS
- ORM models use `Mapped[...]` annotations and `mapped_column(...)`.
- Use explicit table names via `__tablename__` and explicit indexes or `CheckConstraint`s.
- Relationships use `relationship()` only when the code actually needs them.
- Models should be persistence-oriented: columns, constraints, defaults, and relationships only.
- Unique constraints enforce business rules such as unique portfolio slugs, balance labels per portfolio, template names, extension keys, schedule fire keys, versioned platform keys, and quote-cache lookup keys.
- Use mixins from `base.py` instead of repeating `id`, `created_at`, or `updated_at` columns.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not put business logic or validation methods on ORM models.
- Do not hide implicit defaults or rely on database-side behavior without matching app expectations.
- Do not omit indexes for frequently queried lookup paths.
- Do not create relationships just for convenience when ids suffice.
- Do not rename tables or columns casually; tests and startup bootstrap depend on them.
- Do not document retired global authoring tables as live behavior. Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs live inside the current `workflow_packages` JSON artifacts and run-owned snapshots.

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
- `app/models/__init__.py` imports the full preserved-product, extension-state, and agent-platform model surface for startup registration.
- `workflow_package.py` stores current package artifacts without database ids in exported manifests.
- `model_connection.py` stores UI-managed provider endpoint defaults, encrypted API-key payload metadata, status, and last connection-test results.
- `run.py` persists package version identity, package hash, workflow key, queued/running status, execution scope, concurrency policy, lease metadata, attempt counts, per-step outputs, final output, and run totals used by the run monitor.
- `report.py` stores unique `name` and `slug`, tracks the canonical origin `source` values `compiled`, `uploaded`, `external`, and `agent`, and keeps optional metadata in JSONB under the `metadata` column.
- `symbol_name_cache.py` is intentionally `UNLOGGED` because the cache is reconstructible from provider lookups.
- `extension.py` stores `extension_states` rows keyed by statically resident extension key; default enabled state is declared in `app/extensions/registry.py`.
- Legacy global-authoring model files may still exist for startup cleanup or quarantine tests, but Workflow Packages and run-owned snapshots are the live persistence contracts.
