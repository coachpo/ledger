# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds the backend business workflows plus a few stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, while `quote_provider.py` stays stateless, the template/report services keep the preserved product flows intact, and the agent-platform services own agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio CRUD / existence checks | `portfolio_service.py` | shared portfolio lookup boundary for other services |
| Balance workflows | `balance_service.py` | balance CRUD + validation |
| Position workflows | `position_service.py` | manual position CRUD plus symbol-name lookup cache |
| CSV import preview/commit | `csv_import_service.py` | atomic preview/commit contract |
| Trading simulation rules | `trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT + balance/position effects |
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior |
| Template placeholder resolution | `template_compiler_service.py` | `{{portfolios...}}` and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Quote provider contract | `quote_provider.py` | provider protocol, DTOs, Yahoo Finance adapter, provider errors |
| Agent-platform catalog services | `agent_service.py`, `skill_service.py`, `mcp_server_service.py`, `output_schema_service.py`, `workflow_service.py` | immutable versioned CRUD and validation; `skill_service.py` backs canonical capabilities while storage names are deferred |
| Run execution service | `run_service.py` | persisted run lifecycle, per-step detail, and background execution |
| Output-schema compiler | `output_schema_compiler.py` | locked schema-subset validation and runtime model compilation |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_runtime_api.py`, `../../tests/test_runtime_artifacts.py`, `../../tests/test_legacy_backend_cutover.py` | preserved-product regressions, platform execution, and cutover assertions |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Public methods validate portfolio, balance, or position existence before mutating related state.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` owns the provider protocol and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `PositionService` may consult the quote provider to resolve symbol names and caches successful lookups in `symbol_name_cache`; lookup failures should not block manual position CRUD.
- `TemplateCompilerService` resolves the `{{portfolios...}}` and `{{reports...}}` placeholder contract against repositories and powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats compiled reports as timestamped snapshots, uploaded reports as slug-addressed markdown documents with optional metadata, and external JSON reports as first-class persisted sources.
- Agent-platform services keep versioned config immutable, validate typed contracts before save, preserve secret-safe model-connection semantics, and keep run persistence detailed enough for the run monitor.
- Capability terminology is canonical in service docs and API-facing examples. Keep `skill_service.py`, `skills`, `agents.skills`, `skillId`, `skillKey`, and `skillVersion` references only when describing deferred storage or code-level compatibility.
- Service-layer LLM calls must stay inside official SDK clients and service-owned integration boundaries; saved endpoint/key/runtime defaults come from model connections.

## ANTI-PATTERNS
- Do not commit from routers or repositories when a service already owns the workflow.
- Do not bypass repository or service helpers inside trade flows just to mutate ORM models inline.
- Do not treat quote-provider failures as fatal if the existing cache and warning path should keep the request usable.
- Do not change CSV preview or commit payloads without updating backend tests and frontend callers.
- Do not change template placeholder paths or compile payloads without updating backend tests, frontend types, and the template editor.
- Do not change report compile/upload/download contracts, slug generation, or `reports.<name>.content` cycle handling without updating backend tests and frontend callers.
- Do not reintroduce retired service surfaces or compatibility adapters into this folder.
- Do not introduce raw `httpx`/`requests` LLM calling paths in service code.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_runtime_api.py tests/test_runtime_artifacts.py tests/test_legacy_backend_cutover.py
```

## NOTES
- `TradingOperationService` may delete positions on full sell-down and supports DIVIDEND/SPLIT as well as BUY/SELL.
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ModelConnectionService` preserves stored keys on blank edit, records last connection-test results, archives instead of hard-deleting, and masks secrets in user-facing messages.
- `RunService` persists run status, totals, and per-step/per-agent detail for the run monitor.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
