# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds the backend's business workflows plus a few stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, while `quote_provider.py` stays stateless, `template_compiler_service.py` resolves the live placeholder contract, `orchestration_service.py` owns role/character management and mention catalogs, and the runtime v2 execution adapters live under `execution_adapters/`.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio CRUD / existence checks | `portfolio_service.py` | shared portfolio lookup boundary for other services |
| Balance workflows | `balance_service.py` | balance CRUD + validation |
| Position workflows | `position_service.py` | manual position CRUD plus symbol-name lookup cache |
| CSV import preview/commit | `csv_import_service.py` | atomic preview/commit contract |
| Trading simulation rules | `trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT + balance/position effects |
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior |
| Orchestration roles and characters | `orchestration_service.py` | versioned role and character CRUD, mention catalog, reserved-handle and disabled-role checks |
| Template placeholder resolution | `template_compiler_service.py` | `{{portfolios...}}` and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Quote provider contract | `quote_provider.py` | provider protocol, DTOs, Yahoo Finance adapter, provider errors |
| Runtime execution adapters | `execution_adapters/` | frozen-plan execution, approval waits, generic workflow dispatch, single-agent dispatch |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_tryouts_api.py`, `../../tests/test_orchestration_api.py`, `../../tests/test_runtime_execution_adapters.py`, `../../tests/test_runtime_artifacts.py` | CRUD, templates, market-data, symbol cache, orchestration, runtime adapter behavior, and persisted artifact reads |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Public methods validate portfolio, balance, or position existence before mutating related state.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` owns the provider protocol and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `PositionService` may consult the quote provider to resolve symbol names and caches successful lookups in `symbol_name_cache`; lookup failures should not block manual position CRUD.
- `TemplateCompilerService` resolves the `{{portfolios...}}` and `{{reports...}}` placeholder contract against repositories and powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats compiled reports as timestamped snapshots, uploaded reports as slug-addressed markdown documents with optional metadata, and external JSON reports as first-class persisted sources.
- `OrchestrationService` owns versioned orchestration roles and characters, enforces stable keys and handles, protects reserved builtin targets, and returns the mention catalog used by the public API.
- `MarketDataService` is best-effort: provider failures become warnings or cached fallbacks when possible.
- Runtime execution adapters must execute from frozen workflow or agent refs and fail closed on plan drift or widened capability usage.
- `app/services/` stops at backend-side orchestration and runtime adapter dispatch; service-layer code should never make raw HTTP model calls itself.

## ANTI-PATTERNS
- Do not commit from routers or repositories when a service already owns the workflow.
- Do not bypass repository or service helpers inside trade flows just to mutate ORM models inline.
- Do not treat quote-provider failures as fatal if the existing cache and warning path should keep the request usable.
- Do not change CSV preview or commit payloads without updating backend tests and frontend callers.
- Do not change template placeholder paths or compile payloads without updating backend tests, frontend types, and the template editor.
- Do not change report compile/upload/download contracts, slug generation, or `reports.<name>.content` cycle handling without updating backend tests and frontend callers.
- Do not change orchestration role/character contracts, mention catalog behavior, or snapshot upgrade rules without updating backend tests and callers.
- Do not widen capability usage beyond the frozen refs stored for a runtime execution.
- Do not introduce raw `httpx`/`requests` LLM calling paths in service code.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_tryouts_api.py tests/test_orchestration_api.py tests/test_runtime_execution_adapters.py
```

## NOTES
- `TradingOperationService` may delete positions on full sell-down and supports DIVIDEND/SPLIT as well as BUY/SELL.
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
- `OrchestrationService` keeps role/character versions on every edit, forbids reserved builtin handles, and builds a mention catalog from seeded builtin targets plus enabled characters whose roles are enabled.
- Historical simulation-linked rows remain queryable in preserved models, reports, and trading operations until later persistence cleanup tasks remove active code paths.
