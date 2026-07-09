# Backend API Guide

## Overview

API modules are thin FastAPI route adapters over schema models, dependencies, and services.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Platform router | `platform_router.py` | Package-first `/api` routes. |
| Extension router | `router.py` | Installed extension routers under `/api/v1`. |
| Dependencies | `dependencies.py` | Session, repository, service factory wiring. |
| Workflow Packages | `workflow_packages.py` | Package CRUD, import/export, launch, preflight. |
| Schedules | `schedules.py` | Schedule CRUD, preview, fires, run-now. |
| Runs | `runs.py` | Run list/detail/cancel/rerun/delete. |
| Templates/Reports | `templates.py`, `reports.py` | Finance extension `/api/v1` product routes. |
| Tools | `tools.py` | GET-only server-declared tool catalog. |

## Conventions

- `main.py` mounts `platform_router` first, then extension `api_router`.
- Platform APIs live under `/api`; finance extension product APIs live under `/api/v1`.
- Route handlers parse dependencies, call services, and return Pydantic schema objects.
- Keep domain validation, transactions, provider calls, and projection logic out of route handlers.
- Public request/response shape is camelCase through `CamelModel`.
- Raise `ApiError` so responses keep `{code, message, details[]}` and browser-safe filtering.
- Literal routes must remain before parameter catchalls, especially report actions before `/{slug}`.
- Route presence tests should inspect `app.openapi()["paths"]` because FastAPI include-router internals changed after 0.136.

## Anti-Patterns

- Do not mount extension-management routes; extensions are static backend wiring.
- Do not make `/api/tools` mutable.
- Do not expose service exceptions or raw validation internals directly through FastAPI.
