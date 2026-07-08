# BACKEND SERVICES GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file only covers service-layer rules.

## OVERVIEW
`app/services/` holds backend business workflows plus stateless integration boundaries. Persistence-backed domain services own repository orchestration and transactions, static extension contracts own installed extension contributions, finance services keep the `signaldeck.finance` product flows intact, and platform services own Workflow Packages, Scheduled Tasks, Model Connections, Tools, and Runs.

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
| Quote/history/cache logic | `market_data_service.py` | `QuoteProvider`, fallback cache, stale/warning behavior for runtime tools |
| Template placeholder resolution | `template_compiler_service.py` | `{{inputs...}}` and `{{reports...}}` trees, inline compile, stored compile, dynamic selectors, and report re-compilation |
| Stored template CRUD | `text_template_service.py` | unique-name checks, CRUD, compile lookup |
| Report workflows | `report_service.py` | compile from template, external create, upload markdown, slug/name generation, filters, CRUD, download lookup |
| Quote/social provider contracts | `quote_provider.py`, `social_sentiment_provider.py`, `social_sentiment_service.py` | provider protocols, Yahoo/deterministic quotes, Reddit/StockTwits sentiment adapters, degraded warnings |
| Extension composition | `../extensions/registry.py`, `extension_dependencies.py`, `../extensions/signaldeck_finance/provider_factories.py` | installed extension contracts, dependency-only run extension records, and finance provider factory wiring |
| Model gateway / connection truth | `model_gateway.py`, `model_gateway_dto.py`, `model_gateway_openai.py`, `model_gateway_openai_responses.py`, `model_gateway_output_validation.py`, `model_connection_service.py`, `model_connection_probe_service.py`, `model_connection_resolution.py` | persisted model-connection state, capability/probe truth, official-SDK execution, provider retry metadata, tool/schema validation, responses/policy adapters, and protocol DTOs |
| Workflow package services | `workflow_package_service.py`, `workflow_package_preflight.py`, `workflow_package_export.py`, `workflow_package_manifest_parser.py`, `workflow_package_manifest_compiler.py`, `run_input_validation.py` | package-first authoring, validation, import/export, launch input validation, preflight, and immutable package artifacts |
| Scheduled task services | `workflow_package_schedule_service.py`, `workflow_package_schedule_materializer.py` | structured recurrence, IANA timezone occurrence math, scheduled input rendering, idempotent fires, delete cleanup rules, due materialization into queued runs |
| Run planning and execution | `package_execution_plan_builder.py`, `execution_plan.py`, `run_service.py`, `run_rerun.py`, `run_queue_service.py`, `run_read_projection.py`, `../workers/run_scheduler.py`, `execution_providers.py`, `agent_execution_service.py`, `http_operation_execution_service.py` | compiled package planning, queued execution, rerun lineage, backend progress/queue read models, and HTTP/model/tool dispatch |
| MCP runtime boundary | `../agents/mcp/boundaries.py`, `../agents/mcp/runtime.py`, `../agents/mcp/AGENTS.md` | saved config boundary construction and package-private MCP runtime dispatch; active MCP support, not legacy quarantine |
| Output-schema compiler | `output_schema_compiler.py` | locked schema-subset validation and runtime model compilation |
| DI entrypoint | `../api/dependencies.py` | service construction + provider wiring |
| Service test hotspots | `../../tests/test_api.py`, `../../tests/test_extension_contract.py`, `../../tests/test_workflow_package_preflight.py`, `../../tests/test_workflow_package_runtime_api.py`, `../../tests/test_workflow_package_runtime_artifacts.py`, `../../tests/test_workflow_package_run_contracts.py`, `../../tests/test_social_sentiment_service.py` | preserved-product regressions, extension contract, platform execution, provider warnings, and run artifacts |

## CONVENTIONS
- Persistence-backed domain services are constructed with a `Session` and compose repositories or dependent services in `__init__`.
- Multi-step writes commit once inside the service and rollback on exceptions; routers should not manage those transactions.
- Return API-facing read models via `*.model_validate(...)`, not ORM objects.
- `quote_provider.py` and `social_sentiment_provider.py` own provider protocols and data-transfer objects; concrete HTTP response shapes should not leak into service methods.
- `app.extensions.signaldeck_finance.provider_factories` creates quote and social sentiment providers; services consume factories/dependencies instead of constructing providers ad hoc.
- `TemplateCompilerService` resolves the `{{inputs...}}` and `{{reports...}}` placeholder contract against repositories and runtime input maps; it powers inline preview compile, stored-template compile, exact-name report embeds, dynamic report selectors, and report-content re-compilation with cycle detection.
- `ReportService` treats `source` as report origin: `compiled` for template snapshots, `uploaded` for markdown uploads, `external` for true external user/API-created JSON reports, and `agent` for historical agent-origin reports.
- Model-visible prompt and tool-output projections stay report-free: no report ids, slugs, names, raw markdown, URLs, downloads, or audit links.
- `model_gateway*.py` owns provider-protocol execution, output/tool validation, and official-SDK adapter behavior; persisted connection state, capability probes, and capability and runtime-profile truth stay in the `model_connection_*` services.
- Workflow package services keep one mutable current package artifact, validate typed contracts before save, treat private MCP `env`, `headers`, and `query` values as secret-bearing authoring/runtime config that is omitted from browser-visible manifest reads and exports, and keep run persistence detailed enough for snapshot provenance, rerun source links, and the run monitor.
- Scheduled task services keep recurrence and fire semantics backend-owned: structured recurrence only, IANA timezone conversion, placeholder allowlist, preview-before-save validation, idempotent manual fires, delete that removes the schedule and fire rows, stops future automation, preserves existing run history through `scheduleProvenance`, and scheduled or manual fires materialized as ordinary queued package runs.
- `RunService` creates optional Logfire spans, stores formatted top-level trace ids and per-invocation span ids, records dependency-only extension requirements, and falls back to trace-free execution when telemetry setup fails.
- API launch/rerun paths create durable queued rows only; `RunSchedulerWorker` and `RunQueueService` own later claim, lease heartbeat, stale-lease recovery, and claimed execution.
- Tools are global read-only server-declared metadata; package-local capability profiles store only canonical `signaldeck.<owner>.<tool_collection>.<tool>` `toolKeys` and validate against the extension-aware `ToolCatalog`.
- Service-layer LLM calls must stay inside official SDK clients and service-owned integration boundaries; saved endpoint/key/runtime defaults come from global Model Connections.
- Do not add quarantined legacy authoring services for cutover checks; execution and authoring work must use Workflow Package, schedule, Model Connection, and Run services.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not commit from routers or repositories when a service already owns the workflow.
- Do not bypass repository or service helpers inside trade flows just to mutate ORM models inline.
- Do not treat quote-provider failures as fatal if the existing cache and warning path should keep the request usable.
- Do not change template placeholder paths or compile payloads without updating backend tests, frontend types, and the template editor.
- Do not change report compile/upload/download contracts, slug generation, or `reports.<name>.content` cycle handling without updating backend tests and frontend callers.
- Do not bypass static extension contracts or extension-owned factories to expose finance tools/providers.
- Do not add public extension metadata fields to service read models or run dependency records.
- Do not reintroduce retired service surfaces or compatibility adapters into this folder.
- Do not introduce raw `httpx`/`requests` LLM calling paths in service code.

## VALIDATION
```bash
cd backend
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest tests/test_api.py tests/test_extension_contract.py tests/test_tool_catalog_api.py tests/test_workflow_package_preflight.py tests/test_mcp_runtime.py tests/test_social_sentiment_service.py tests/test_workflow_package_runtime_api.py tests/test_workflow_package_runtime_artifacts.py tests/test_workflow_package_run_contracts.py
```

## NOTES
- `MarketDataService` caches quotes by provider/symbol/as-of and recomputes staleness when falling back to cached rows.
- `ModelConnectionService` preserves stored keys on blank edit, records last connection-test results, archives instead of hard-deleting, and masks secrets in user-facing messages.
- `RunService` persists run status, totals, package provenance, optional Logfire trace/span identifiers, scheduled run/fire metadata, rerun lineage, dependency-only extension records, and per-step/per-agent detail for the run monitor.
- `ReportService` lists newest-first, accepts markdown uploads up to 2 MB, supports direct external JSON creation, and stores optional author/description/tags/analysis metadata in JSONB.
- `backend/app/services/providers/` is effectively reserved right now; keep provider/runtime seams in provider factories and gateway services until a real subpackage boundary exists.
