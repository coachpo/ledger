# BACKEND API GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers route modules and dependency wiring in `app/api/`.

## OVERVIEW
`app/api/` owns FastAPI `APIRouter` modules, request/response contracts, dependency wiring, and translation from service-layer errors into HTTP responses. Routers stay thin and delegate business rules to services. The live app mounts the preserved `/api/v1` product routes plus the current `/api/*` agent-platform routes.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Router composition | `router.py`, `platform_router.py`, `../main.py` | `router.py` composes `/api/v1`, `platform_router.py` composes `/api/*`, and `main.py` mounts both |
| Service construction | `dependencies.py` | request-scoped session plus CRUD, trading, market-data, template, report, model-connection, and agent-platform service factories |
| Portfolio routes | `portfolios.py` | portfolio CRUD |
| Balance routes | `balances.py` | portfolio-scoped balance CRUD |
| Position routes | `positions.py` | portfolio-scoped position CRUD plus symbol lookup |
| Trading routes | `trading_operations.py` | simulated BUY/SELL/DIVIDEND/SPLIT operations |
| Market data routes | `market_data.py` | delayed quote/history endpoints |
| Template routes | `templates.py` | CRUD, placeholder tree, inline compile, stored compile |
| Report routes | `reports.py` | filterable list/detail, compile from template, external create, upload markdown, edit, delete, download |
| Agent-platform routes | `workflow_packages.py`, `model_connections.py`, `tools.py`, `runs.py` | live `/api/*` routes for Workflow Packages, Model Connections, Tools, and Runs |
| Shared API handlers | `../main.py`, `../core/errors.py` | healthcheck plus global error translation |

## CONVENTIONS
- Each module declares one `APIRouter(prefix=..., tags=[...])`.
- `main.py` mounts `/api/v1` via `router.py` and `/api/*` via `platform_router.py`.
- Route handlers accept integer ids from the path and typed Pydantic bodies where applicable, then delegate to a service.
- Use `Depends(get_...)` factories from `dependencies.py` rather than constructing services inline.
- Keep routes RESTful: HTTP verbs express intent, and success responses match the declared `response_model`.
- Routes should let service-layer `ApiError` exceptions and request-validation failures bubble to the handlers in `app/main.py`.
- Template routes split stored-template CRUD from compile-only endpoints; placeholder browsing is read-only.
- Report routes are slug-addressed after creation; the list endpoint supports metadata filters (`ticker`, `tag`, `reviewType`, `portfolioSlug`, `source`, `limit`, `offset`), where `source` filters the canonical report origins `compiled`, `uploaded`, `external`, and `agent`. Compile combines `TextTemplateService`, `TemplateCompilerService`, and `ReportService`; upload uses `multipart/form-data` markdown plus optional metadata; `POST /reports` supports direct true external JSON creation only. Agent-created reports use `source="agent"`; `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"` describe memory-report purpose/type, and server-owned `metadata.createdBy.type="agent"` carries provenance such as `runId`, `agentKey`, and `agentVersion`.
- Do not hand-build camelCase responses; let `CamelModel` serialize them.
- Workflow package routes are canonical for platform authoring. The only mounted platform routers are Workflow Packages, Model Connections, Tools, and Runs. Package manifests keep agents, output schemas, capability profiles, private MCP configs, and workflow graphs package-private. Legacy global authoring modules such as `agents.py`, `capabilities.py`, `mcp_servers.py`, `output_schemas.py`, and `workflows.py` are unmounted cutover context only. Do not change runtime tool keys or OpenAI function names.

## ANTI-PATTERNS
- Do not put business rules or DB logic in route handlers.
- Do not instantiate `Session()` or repositories directly in routes.
- Do not swallow `ApiError` exceptions just to remap status codes manually.
- Do not bypass dependencies when wiring services, template helpers, report helpers, model-connection helpers, platform helpers, or quote providers.
- Do not duplicate request validation already captured by schemas.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_workflow_package_openapi.py tests/test_workflow_package_runtime_api.py tests/test_legacy_backend_cutover.py
```

## NOTES
- `router.py` mounts the live `/api/v1` routers for portfolios, balances, positions, trading operations, market data, templates, and reports.
- `platform_router.py` mounts the live `/api/*` routers for workflow packages, model connections, tools, and runs.
- `dependencies.py` constructs services with a shared request `Session` and wires the preserved product services, model-connection service, tool catalog, workflow package services, and run service into the live API.
