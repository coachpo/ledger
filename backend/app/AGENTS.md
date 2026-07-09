# Backend App Guide

## Overview

FastAPI app code is a thin API layer over SQLAlchemy repositories, orchestration services, static runtime tools, and bundled extensions.

## Structure

| Path | Purpose |
| --- | --- |
| `api/` | FastAPI routers and dependencies. |
| `core/` | Config, auth middleware, errors, telemetry. |
| `db/` | Engine/session lifecycle, `create_all`, seeds, startup recovery. |
| `models/` | SQLAlchemy persistence models and encrypted JSON type. |
| `schemas/` | Pydantic external API contracts. |
| `repositories/` | Session-scoped data access and queue/schedule claims. |
| `services/` | Transactions, orchestration, runtime execution, validation projection. |
| `agents/` | MCP adapters, runtime tool registry, tool catalog. |
| `extensions/` | Static bundled extensions. |
| `workers/` | Scheduler process entry point. |

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| App factory and routers | `main.py` | `/api` platform router plus `/api/v1` extension router. |
| Route dependencies | `api/dependencies.py` | Service/repository factories live here. |
| API schemas | `schemas/common.py` | `CamelModel` owns aliases, `extra="forbid"`, serialization. |
| Error envelopes | `core/errors.py` | Use `ApiError`, not ad hoc `HTTPException`. |
| DB lifecycle | `db/session.py` | No migrations; startup creates and recovers. |
| Run persistence | `models/run.py` | Immutable package snapshots and run guards. |
| Runtime tools | `agents/runtime_tools/registry.py` | Static tool dispatch, grant checks, context. |

## Conventions

- API routes are adapters: parse dependencies, call services, return schema objects.
- Platform APIs mount under `/api`; extension product APIs mount under `/api/v1`.
- Backend internals use snake_case; external JSON uses camelCase aliases through `CamelModel`.
- Repositories are query/persistence boundaries. Put business rules, transactions, and projections in services.
- Secrets persist only in encrypted payload columns or runtime-only settings and must be redacted from reads, logs, exports, diagnostics, and error details.
- Run Workflow Package executions must keep immutable `RunWorkflowPackageSnapshot` records.
- Runtime tools are statically contributed by installed extensions and grant-checked before execution.
- There is no `backend/app/runtime` package; runtime behavior lives in `agents/`, `services/`, and `extensions/`.

## Anti-Patterns

- Do not add Alembic or partial migration shims without re-scoping the DB strategy.
- Do not let route handlers own transactions or domain validation.
- Do not access package secrets while building browser-visible payloads.
- Do not add dynamic plugin discovery or marketplace behavior.
