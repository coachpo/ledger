# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds the backend business workflows plus a few stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, while `quote_provider.py` stays stateless, the template/report services keep the preserved product flows intact, and the agent-platform services own Workflow Packages, Model Connections, Tools, and Runs.

The application is under active development and has no users at the moment; future upgrade, migration, and compatibility design must account for that and should not preserve speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Portfolio CRUD / existence checks | `portfolio_service.py` | shared portfolio lookup boundary for other services |
| Balance workflows | `balance_service.py` | balance CRUD + validation |
| Position workflows | `position_service.py` | manual position CRUD plus symbol-name lookup cache |
| CSV import preview/commit | `csv_import_service.py` | atomic preview/commit contract |
| Trading simulation rules | `trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT + balance/position effects |
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior |
| Template placeholder resolution | `template_compiler_service.py` | `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Memory workflows | `memory_service.py`, `memory_report_service.py`, `memory_context_service.py`, `report_backed_memory_store.py`, `memory_store.py` | memory DTO lifecycle, report-backed persistence, prompt snippets, and audit links |
| Quote provider contract | `quote_provider.py` | provider protocol, DTOs, Yahoo Finance adapter, provider errors |
| Workflow package services | `workflow_package_service.py`, `workflow_package_preflight.py`, `workflow_package_export.py`, `workflow_package_manifest_parser.py`, `workflow_package_manifest_compiler.py`, `workflow_package_manifest_decompiler.py` | package-first authoring, validation, import/export, preflight, and immutable package artifacts |
| Run execution service | `run_service.py` | persisted global run lifecycle, package provenance, Logfire trace/span metadata, per-step detail, and background execution |
| Output-schema compiler | `output_schema_compiler.py` | locked schema-subset validation and runtime model compilation |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_workflow_package_runtime_api.py`, `../../tests/test_workflow_package_runtime_artifacts.py`, `../../tests/test_workflow_package_run_contracts.py`, `../../tests/test_memory_reports.py`, `../../tests/test_legacy_backend_cutover.py` | preserved-product regressions, platform execution, memory reports, run artifacts, and cutover assertions |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Public methods validate portfolio, balance, or position existence before mutating related state.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` owns the provider protocol and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `PositionService` may consult the quote provider to resolve symbol names and caches successful lookups in `symbol_name_cache`; lookup failures should not block manual position CRUD.
- `TemplateCompilerService` resolves the `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` placeholder contract against repositories and runtime input maps; it powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats `source` as report origin: `compiled` for template snapshots, `uploaded` for markdown uploads, `external` for true external user/API-created JSON reports, and `agent` for agent-created reports. Agent-memory report purpose stays in `metadata.analysis.reviewType="agent_memory"` with `metadata.analysis.versionGroup="agent_memory/v1"`; server-owned `metadata.createdBy.type="agent"` records provenance such as `runId`, `agentKey`, and `agentVersion`.
- Phase 1 memory stays report backed. `ReportBackedMemoryStore` is the only service-layer component that may parse or format `mem_<report_id>`; `MemoryService`, prompt assembly, runtime tools, run artifacts, and callers treat `memoryId` values as opaque strings.
- Phase 1 does not have vector search, embeddings, or a memory table. Memory lookup remains metadata-filter based over report-backed rows.
- Model-visible prompt and tool-output projections stay report-free: no report ids, slugs, names, raw markdown, URLs, downloads, or audit links. API/UI projections may include nested `auditLinks.report` only for human audit actions.
- Workflow package services keep package versions immutable, validate typed contracts before save, keep private MCP `env`, `headers`, and `query` values inline through import/export, and keep run persistence detailed enough for package provenance and the run monitor.
- `RunService` creates optional Logfire spans, stores formatted top-level trace ids and per-invocation span ids, and falls back to trace-free execution when telemetry setup fails.
- Tools are global read-only server-declared metadata; package-local capability profiles store `toolKeys` and validate against `ToolCatalog`.
- Service-layer LLM calls must stay inside official SDK clients and service-owned integration boundaries; saved endpoint/key/runtime defaults come from global Model Connections.

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
uv run pytest tests/test_api.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_runtime_artifacts.py tests/test_workflow_package_run_contracts.py tests/test_memory_reports.py tests/test_legacy_backend_cutover.py
```

## NOTES
- `TradingOperationService` may delete positions on full sell-down and supports DIVIDEND/SPLIT as well as BUY/SELL.
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ModelConnectionService` preserves stored keys on blank edit, records last connection-test results, archives instead of hard-deleting, and masks secrets in user-facing messages.
- `RunService` persists run status, totals, package provenance, optional Logfire trace/span identifiers, rerun/step-replay lineage, memory artifact report links, and per-step/per-agent detail for the run monitor.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
B.
