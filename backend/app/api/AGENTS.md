# BACKEND API GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers route modules and dependency wiring in `app/api/`.

## OVERVIEW
`app/api/` owns FastAPI `APIRouter` modules, request/response contracts, dependency wiring, and translation from service-layer errors into HTTP responses. Routers stay thin and delegate business rules to services.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Router composition | `router.py` | mounts all route modules under `/api/v1` |
| Service construction | `dependencies.py` | request-scoped session plus CRUD, CSV import, trading, market-data, template, report, orchestration, and quote-provider factories |
| Portfolio routes | `portfolios.py` | portfolio CRUD |
| Balance routes | `balances.py` | portfolio-scoped balance CRUD |
| Position routes | `positions.py` | portfolio-scoped position CRUD plus symbol lookup |
| Backtest routes | `backtests.py` | create/list/get/cancel/delete for backtest rows and launch semantics |
| Backtest callback routes | `backtest_callbacks.py` | cycle report upload, trade execution, and cycle-complete ingress for the retained legacy callback surface |
| Trading routes | `trading_operations.py` | simulated BUY/SELL/DIVIDEND/SPLIT operations |
| Market data routes | `market_data.py` | delayed quote/history endpoints |
| Orchestration routes | `orchestration.py` | role CRUD, character CRUD, mention catalog |
| Template routes | `templates.py` | CRUD, placeholder tree, inline compile, stored compile |
| Report routes | `reports.py` | filterable list/detail, compile from template, external create, upload markdown, edit, delete, download |
| Shared API handlers | `../main.py`, `../core/errors.py` | healthcheck plus global error translation |

## CONVENTIONS
- Each module declares one `APIRouter(prefix=..., tags=[...])`.
- Route handlers accept integer ids from the path and typed Pydantic bodies, then delegate to a service.
- Use `Depends(get_...)` factories from `dependencies.py` rather than constructing services inline.
- Keep routes RESTful: HTTP verbs express intent, and success responses match the declared `response_model`.
- Routes should let service-layer `ApiError` exceptions and request-validation failures bubble to the handlers in `app/main.py`.
- Template routes split stored-template CRUD from compile-only endpoints; placeholder browsing is read-only.
- Upload-specific checks such as report file size, markdown file type, and text decoding stay in routes because they are HTTP-layer concerns; validated content then delegates to `ReportService`.
- Report routes are slug-addressed after creation; the list endpoint supports metadata filters (`ticker`, `tag`, `reviewType`, `portfolioSlug`, `source`, `limit`, `offset`), compile combines `TextTemplateService`, `TemplateCompilerService`, and `ReportService`, upload uses `multipart/form-data` markdown plus optional metadata, and `POST /reports` supports direct external JSON creation.
- Orchestration routes expose versioned role and character CRUD plus the mention catalog used by prompt-time orchestration surfaces.
- Backtest routes are split by responsibility: `backtests.py` owns CRUD/lifecycle endpoints, while `backtest_callbacks.py` retains `/backtests/{id}/cycles/{date}/report|trades|complete` compatibility ingress even though the normal execution path is now internal LangGraph.
- Callback routes accept a numeric backtest id plus cycle date, then delegate to `BacktestCycleService`; they should not embed webhook-state logic inline.
- Do not hand-build camelCase responses; let `CamelModel` serialize them.

## ANTI-PATTERNS
- Do not put business rules or DB logic in route handlers.
- Do not instantiate `Session()` or repositories directly in routes.
- Do not swallow `ApiError` exceptions just to remap status codes manually.
- Do not bypass dependencies when wiring services, template helpers, orchestration helpers, or quote providers.
- Do not duplicate request validation already captured by schemas.

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
- `router.py` mounts all live routers under `/api/v1`: backtests, backtest callbacks, portfolios, balances, positions, trading operations, market data, orchestration, templates, and reports.
- `dependencies.py` constructs services with a shared request `Session` and wires `BacktestService`, `BacktestCycleService`, `OrchestrationService`, `CsvImportService`, `TradingOperationService`, `MarketDataService`, `TextTemplateService`, `TemplateCompilerService`, `ReportService`, and `YahooFinanceQuoteProvider` into the live API.
