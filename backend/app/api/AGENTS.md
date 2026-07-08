# BACKEND API GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers route modules and dependency wiring in `app/api/`.

## OVERVIEW
`app/api/` owns FastAPI `APIRouter` modules, request/response contracts, dependency wiring, and translation from service-layer errors into HTTP responses. Routers stay thin and delegate business rules to services. The live app mounts preserved `/api/v1` finance routes through `signaldeck.finance` registrations plus current `/api/*` platform routes for Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Tools, and Runs.

Extension model: statically resident `signaldeck.finance` registrations.

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
| Router composition | `router.py`, `platform_router.py`, `../main.py` | `router.py` includes `signaldeck.finance` `/api/v1` registrations, `platform_router.py` composes `/api/*`, and `main.py` mounts both |
| Service construction | `dependencies.py` | request-scoped session plus finance extension, extension state, model-connection, tool-catalog, workflow-package, schedule, and run service factories |
| Template routes | `templates.py` | CRUD, placeholder tree, inline compile, stored compile |
| Report routes | `reports.py` | filterable list/detail, compile from template, external create, upload markdown, edit, delete, download |
| Platform routes | `workflow_packages.py`, `schedules.py`, `model_connections.py`, `extensions.py`, `tools.py`, `runs.py` | live `/api/*` routes for Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Tools, and Runs, including rerun endpoints under Runs |
| Finance route registrations | `../extensions/signaldeck_finance/api_routers.py` | extension-gated `/api/v1` registration list for preserved finance routes |
| Retired global authoring APIs | `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/api/v1/templates/seed`, `/api/v1/orchestration/*`, `/api/v2/*` | not live route modules; do not recreate them as compatibility aliases |
| Shared API handlers | `../main.py`, `../core/errors.py` | healthcheck plus global error translation |

## CONVENTIONS
- Each live module declares one `APIRouter(prefix=..., tags=[...])`.
- `main.py` mounts `/api/v1` via `router.py` and `/api/*` via `platform_router.py`; `/api/v1` route registrations come from `app.extensions.signaldeck_finance.api_routers` and carry `require_extension_enabled()` dependencies.
- Route handlers accept integer ids from the path and typed Pydantic bodies where applicable, then delegate to a service.
- Use `Depends(get_...)` factories from `dependencies.py` rather than constructing services inline.
- Keep routes RESTful: HTTP verbs express intent, and success responses match the declared `response_model`.
- Routes should let service-layer `ApiError` exceptions and request-validation failures bubble to the handlers in `app/main.py`.
- Template routes split stored-template CRUD from compile-only endpoints; placeholder browsing is read-only.
- Report routes are slug-addressed after creation; the list endpoint supports metadata filters (`ticker`, `tag`, `reviewType`, `source`, `limit`, `offset`), where `source` filters the canonical report origins `compiled`, `uploaded`, `external`, and `agent`. Compile combines `TextTemplateService`, `TemplateCompilerService`, and `ReportService`; upload uses `multipart/form-data` markdown plus optional metadata; `POST /reports` supports direct true external JSON creation only.
- Do not hand-build camelCase responses; let `CamelModel` serialize them.
- Workflow Package routes are canonical for platform authoring. The mounted platform routers are Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Tools, and Runs. Package manifests keep agents, output schemas, capability profiles, private MCP configs, and workflow graphs package-private.
- Scheduled Task routes expose package-first automation only: list/detail/create/update/delete, fire history, unsaved/saved preview, and run-now. They delegate recurrence, template rendering, idempotency, run materialization, and schedule-owned cleanup to services.
- Legacy global authoring route modules plus `/api/v1/templates/seed`, `/api/v1/orchestration/*`, and `/api/v2/*` are not live API modules. Do not recreate them, remount them, document them as live, or treat them as compatibility aliases.
- Do not change runtime tool keys or OpenAI function names here.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not put business rules or DB logic in route handlers.
- Do not instantiate `Session()` or repositories directly in routes.
- Do not swallow `ApiError` exceptions just to remap status codes manually.
- Do not bypass dependencies when wiring services, extension gates, template helpers, report helpers, model-connection helpers, platform helpers, or quote providers.
- Do not duplicate request validation already captured by schemas.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_extensions_api.py tests/test_extension_lifecycle_matrix.py tests/test_workflow_package_openapi.py tests/test_workflow_package_runtime_api.py
```

## NOTES
- `router.py` mounts the live `/api/v1` finance routers returned by `signaldeck_finance.api_routers.register()`.
- `platform_router.py` mounts the live `/api/*` routers for workflow packages, schedules, model connections, extensions, tools, and runs.
- `dependencies.py` constructs services with a shared request `Session` and wires finance extension services, extension state service, model-connection service, tool catalog, workflow package services, schedule services, and run service into the live API.
