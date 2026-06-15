# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds backend business workflows plus stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, `ExtensionService` owns statically resident extension state/filtering, finance services keep the `signaldeck.finance` product flows intact, and platform services own Workflow Packages, Scheduled Tasks, Model Connections, Extensions, Tools, memory, and Runs.

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
| Portfolio CRUD / existence checks | `portfolio_service.py` | shared portfolio lookup boundary for other services |
| Balance workflows | `balance_service.py` | balance CRUD + validation |
| Position workflows | `position_service.py` | manual position CRUD plus symbol-name lookup cache |
| CSV import preview/commit | `csv_import_service.py` | atomic preview/commit contract |
| Trading simulation rules | `trading_operation_service.py` | BUY/SELL/DIVIDEND/SPLIT + balance/position effects |
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior |
| Template placeholder resolution | `template_compiler_service.py` | `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, and report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Memory workflows | `memory_service.py`, `memory_context_service.py`, `memory_store.py`, `memory_follow_up_service.py`, `memory_report_service.py` | core memory visibility contract, Postgres persistence, follow-up evaluation, prompt snippets, run evidence, and historical report-domain readers |
| Quote/social provider contracts | `quote_provider.py`, `social_sentiment_provider.py`, `social_sentiment_service.py` | provider protocols, Yahoo/deterministic quotes, Reddit/StockTwits sentiment adapters, degraded warnings |
| Extension state/filtering | `extension_service.py`, `extension_dependency_service.py`, `extension_gate.py`, `../extensions/signaldeck_finance/provider_factories.py` | slim statically resident extension state, surface gating, ToolCatalog/runtime registry filtering, dependency-only run extension records, and finance provider factory wiring |
| Model gateway / connection truth | `model_gateway.py`, `model_gateway_dto.py`, `model_gateway_openai.py`, `model_gateway_openai_responses.py`, `model_gateway_output_validation.py`, `model_gateway_policy_strategy.py`, `model_gateway_provider_retry.py`, `model_gateway_tool_strategy.py`, `model_gateway_tool_retry.py`, `model_connection_service.py`, `model_connection_probe_service.py`, `model_connection_compatibility.py`, `model_connection_snapshot.py` | persisted model-connection state, capability/probe truth, official-SDK execution, provider retry metadata, tool/schema validation, responses/policy adapters, and protocol DTOs |
| Workflow package services | `workflow_package_service.py`, `workflow_package_preflight.py`, `workflow_package_export.py`, `workflow_package_manifest_parser.py`, `workflow_package_manifest_compiler.py`, `workflow_package_manifest_decompiler.py`, `workflow_package_runtime_input_registry.py`, `workflow_package_runtime_inputs.py` | package-first authoring, validation, import/export, runtime-input registry/history, preflight, and immutable package artifacts |
| Scheduled task services | `workflow_package_schedule_service.py`, `workflow_package_schedule_materializer.py` | structured recurrence, IANA timezone occurrence math, scheduled input rendering, idempotent fires, delete cleanup rules, due materialization into queued runs |
| Run planning and execution | `package_execution_plan_builder.py`, `execution_plan.py`, `run_service.py`, `run_rerun_fork.py`, `run_queue_service.py`, `run_read_projection.py`, `../workers/run_scheduler.py`, `run_lifecycle.py`, `execution_providers.py`, `agent_execution_service.py`, `http_operation_execution_service.py` | compiled package planning, queued execution, rerun/fork lineage, backend progress/queue read models, lifecycle hooks, and HTTP/model/tool dispatch |
| Output-schema compiler | `output_schema_compiler.py` | locked schema-subset validation and runtime model compilation |
| Legacy cutover helpers | `legacy_authoring.py`, `agent_service.py`, `workflow_service.py`, `capability_service.py`, `mcp_server_service.py`, `output_schema_service.py`, `agent_manifest_*`, `workflow_manifest_*`, `execution_plan_builder.py` | quarantine/upgrade-only legacy authoring context; not live route or package-first service surfaces |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_extensions_api.py`, `../../tests/test_extension_lifecycle_matrix.py`, `../../tests/test_workflow_package_preflight.py`, `../../tests/test_workflow_package_runtime_api.py`, `../../tests/test_workflow_package_runtime_artifacts.py`, `../../tests/test_workflow_package_run_contracts.py`, `../../tests/test_memory_service.py`, `../../tests/test_social_sentiment_service.py`, `../../tests/test_legacy_backend_cutover.py` | preserved-product regressions, extension state, platform execution, core memory, provider warnings, run artifacts, and cutover assertions |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Public methods validate portfolio, balance, or position existence before mutating related state.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` and `social_sentiment_provider.py` own provider protocols and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `app.extensions.signaldeck_finance.provider_factories` creates quote and social sentiment providers; services consume factories/dependencies instead of constructing providers ad hoc.
- `PositionService` may consult the quote provider to resolve symbol names and caches successful lookups in `symbol_name_cache`; lookup failures should not block manual position CRUD.
- `TemplateCompilerService` resolves the `{{inputs...}}`, `{{portfolios...}}`, and `{{reports...}}` placeholder contract against repositories and runtime input maps; it powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats `source` as report origin: `compiled` for template snapshots, `uploaded` for markdown uploads, `external` for true external user/API-created JSON reports, and `agent` for historical agent-origin reports. Historical agent-memory report purpose stays in `metadata.analysis.reviewType="agent_memory"`, but canonical memory writes and lookup do not use reports as storage.
- Phase 1 memory is platform-core. `MemoryService` defaults to `PostgresMemoryStore`, `memoryId` and `revisionId` values are opaque, and run evidence persists in `run_memory_events`.
- Phase 1 admin hard delete is single-entry only: it removes the entry and dependent revisions/chunks/embeddings through existing cascades while preserving `run_memory_events` as run evidence with snapshot string ids and nullable numeric memory FKs. Runtime delete, bulk delete, delete events, tombstones, and run/package ownership cascades are non-goals.
- Phase 1 does not have vector search, embeddings browser, or chunk-table browser. Runtime memory lookup remains scoped, workflow-visible-only, and deterministic over core memory entries and revisions. Runtime writes default hidden, admin create defaults visible, and admin list defaults to all entries with optional visibility filtering.
- Model-visible prompt and tool-output projections stay report-free: no report ids, slugs, names, raw markdown, URLs, downloads, or audit links. API/UI projections may include nested `auditLinks.report` only for human audit actions.
- `model_gateway*.py` owns provider-protocol execution, output/tool validation, and official-SDK adapter behavior; persisted connection state, capability probes, and compatibility truth stay in the `model_connection_*` services.
- Workflow package services keep one mutable current package artifact, validate typed contracts before save, treat private MCP `env`, `headers`, and `query` values as secret-bearing authoring/runtime config that is omitted from browser-visible manifest reads and exports, and keep runtime-input registry/history plus run persistence detailed enough for snapshot provenance, rerun/fork lineage, and the run monitor.
- Scheduled task services keep recurrence and fire semantics backend-owned: structured recurrence only, IANA timezone conversion, placeholder allowlist, preview-before-save validation, idempotent manual fires, delete that removes the schedule and fire rows, stops future automation, preserves existing run history through `scheduleProvenance`, and scheduled or manual fires materialized as ordinary queued package runs.
- `ExtensionService` is the service-layer authority for enabled extension keys, `/api/extensions` toggles, extension-filtered ToolCatalog/runtime registries, execution provider bundles, and run lifecycle hooks.
- `RunService` creates optional Logfire spans, stores formatted top-level trace ids and per-invocation span ids, records dependency-only extension requirements, and falls back to trace-free execution when telemetry setup fails.
- API launch/rerun/fork paths create durable queued rows only; `RunSchedulerWorker` and `RunQueueService` own later claim, lease heartbeat, stale-lease recovery, and claimed execution.
- Tools are global read-only server-declared metadata; package-local capability profiles store only canonical `signaldeck.<owner>.<tool_collection>.<tool>` `toolKeys` and validate against the extension-aware `ToolCatalog`.
- Service-layer LLM calls must stay inside official SDK clients and service-owned integration boundaries; saved endpoint/key/runtime defaults come from global Model Connections.
- Quarantined legacy authoring services may remain for cutover tests and schema cleanup, but new execution and authoring work must use Workflow Package, schedule, Model Connection, Memory, and Run services.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not commit from routers or repositories when a service already owns the workflow.
- Do not bypass repository or service helpers inside trade flows just to mutate ORM models inline.
- Do not treat quote-provider failures as fatal if the existing cache and warning path should keep the request usable.
- Do not change CSV preview or commit payloads without updating backend tests and frontend callers.
- Do not change template placeholder paths or compile payloads without updating backend tests, frontend types, and the template editor.
- Do not change report compile/upload/download contracts, slug generation, or `reports.<name>.content` cycle handling without updating backend tests and frontend callers.
- Do not bypass `ExtensionService` or extension-owned factories to expose finance tools/providers when `signaldeck.finance` is disabled.
- Do not add public extension metadata fields to service read models or run dependency records. Keep public state limited to `key`, `label`, and `enabled`.
- Do not reintroduce retired service surfaces or compatibility adapters into this folder.
- Do not introduce raw `httpx`/`requests` LLM calling paths in service code.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_extensions_api.py tests/test_extension_lifecycle_matrix.py tests/test_workflow_package_preflight.py tests/test_social_sentiment_service.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_runtime_artifacts.py tests/test_workflow_package_run_contracts.py tests/test_memory_reports.py tests/test_legacy_backend_cutover.py
```

## NOTES
- `TradingOperationService` may delete positions on full sell-down and supports DIVIDEND/SPLIT as well as BUY/SELL.
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ModelConnectionService` preserves stored keys on blank edit, records last connection-test results, archives instead of hard-deleting, and masks secrets in user-facing messages.
- `RunService` persists run status, totals, package provenance, optional Logfire trace/span identifiers, scheduled run/fire metadata, rerun/fork lineage, dependency-only extension records, and per-step/per-agent detail for the run monitor.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
- `ExtensionService` reads private bundled registry wiring, persists slim toggle state when changed, and keeps tool discovery/runtime dispatch aligned with enabled extensions.
- `backend/app/services/providers/` is effectively reserved right now; keep provider/runtime seams in provider factories and gateway services until a real subpackage boundary exists.
