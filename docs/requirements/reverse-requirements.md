# Reverse-Engineered Requirements Document

> Status: Reverse-engineered from the live `main` implementation on 2026-06-09.
> Evidence policy: live code and tests outrank existing docs when they conflict; existing docs are treated as corroborating evidence only.

## 1. Executive Summary

SignalDeck appears to be a single-repository product that combines a finance workspace with a package-first agents workflow platform. The shipped browser surface centers on extension-gated finance features (`dashboard`, `portfolios`, `templates`, `reports`) plus platform-owned workflow package authoring, scheduled task automation, model connections, runs, extensions, and explicit-scope memory.

The strongest confirmed product boundary is that executable workflows enter and run only as Workflow Packages. The codebase also enforces a second strong boundary between platform-core behavior and extension-owned behavior: `signaldeck.finance` owns preserved finance routes, nav, and tools, while `signaldeck.digital_oracle` is bundled but tool-only.

## 2. Scope

### In Scope

- Extension-gated finance workspace routes for dashboard, portfolios, templates, and reports.
- Preserved finance APIs under `/api/v1` for portfolios, balances, positions, trading operations, market data, templates, and reports.
- Platform APIs under `/api` for workflow packages, schedules, model connections, extensions, tools, memory, and runs.
- Workflow Package manifest authoring, validation, import/export, launch metadata, and queued launch creation.
- Package-local secret bindings, package-local runtime input registry entries, and package-local HTTP operation nodes.
- Scheduled Tasks with structured recurrence, previews, run-now behavior, fire history, and schedule provenance.
- Global Model Connections, slim bundled Extensions state, read-only Tools metadata, global Runs, and platform-core Memory.

### Out of Scope / Not Evidenced

- Multi-user authentication, authorization, tenancy, or account management as live product behavior; the current product contract is trusted single-user.
- Live broker execution, realtime market streaming, or autonomous trading.
- Legacy global authoring surfaces for agents, capabilities, MCP servers, output schemas, or workflows.
- Studio, Tryout, orchestration, runtime-v2, simulations, backtests, or `/skills*` surfaces.
- Public global memory CRUD or unscoped memory search.
- Any Digital Oracle route or navigation surface; the bundled Digital Oracle extension is tool-only.
- Long-term backward-compatibility guarantees for Workflow Package import/export beyond the current live contract.
- User-facing latency, throughput, or SLA guarantees for queued run execution.
- Formal WCAG/accessibility conformance targets, localization frameworks, or multilingual UI content.
- Formal privacy, regulatory, or retention policy beyond the technical controls and explicit persistence/delete semantics evidenced in code and tests.

## 3. Actors and Roles

SignalDeck's live product contract is a trusted single-user workspace. The code does not implement a separate authenticated role model; the remaining "roles" in this section are capability groupings or system actors over the same browser/API surface.

| Actor | Description | Permissions / capabilities | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| Trusted operator | Primary human user of the browser and API surfaces. | Can create and manage portfolios, templates, reports, workflow packages, schedules, model connections, and runs; can view and toggle bundled extensions; and can inspect, resolve, and reflect scoped memory. | `frontend/src/routes.ts`, `backend/app/api/*.py`, `backend/app/api/memory.py`, `backend/app/api/extensions.py`, `docs/prd.md` | Medium |
| Workflow package author | Operator acting specifically in package authoring and launch flows. | Can author package-local agents, schemas, capability profiles, MCP configs, workflows, secrets, launch inputs, and launches. | `frontend/src/pages/workflow-packages/*`, `backend/app/api/workflow_packages.py` | High |
| Scheduler worker | Internal runtime actor, not a browser persona. | Materializes due schedules, claims queued runs, heartbeats leases, recovers stale leases, and hands execution to `RunService`. | `backend/app/workers/run_scheduler.py` | High |
| External provider systems | Supporting systems rather than user personas. | Supply quotes, model execution, MCP responses, prediction markets, SEC filings, and market sentiment data. | `backend/app/core/config.py`, `backend/app/services/model_gateway*.py`, `backend/app/extensions/signaldeck_digital_oracle/*` | High |

Only the trusted operator is evidenced as a human access role. `Workflow package author` is a capability mode of that same operator, while the scheduler worker and external providers are system actors rather than separate permission roles.

## 4. Domain Glossary

| Term | Meaning | Evidence |
| --- | --- | --- |
| Workflow Package | The only live executable workflow authoring artifact; a YAML manifest plus compiled plan. | `README.md`, `backend/app/api/workflow_packages.py`, `backend/app/models/workflow_package.py` |
| Model Connection | A global saved provider/model binding with secret-safe reads and backend-owned compatibility data. | `backend/app/api/model_connections.py`, `backend/app/models/model_connection.py` |
| Scheduled Task | A recurring automation record targeting one current Workflow Package workflow. | `backend/app/api/schedules.py`, `backend/app/models/workflow_package_schedule.py` |
| Schedule Fire | A persisted materialized occurrence of a schedule, with queued/skipped/failed status and rendered parameters. | `backend/app/models/workflow_package_schedule.py` |
| Run | A queued or executed workflow-package run with immutable package provenance and execution evidence. | `backend/app/api/runs.py`, `backend/app/models/run.py`, `backend/app/schemas/run.py` |
| Rerun | A descendant run created by editing root launch parameters. | `backend/app/api/runs.py`, `backend/tests/test_workflow_package_run_contracts.py` |
| Fork | A descendant run created by editing one selected agent invocation input. | `backend/app/api/runs.py`, `backend/app/models/run_fork.py` |
| Extension | A statically resident bundled owner for routes, tools, or providers, exposed publicly only as `{key,label,enabled}`. | `backend/app/extensions/registry.py`, `backend/app/services/extension_service.py` |
| Server-declared tool | Read-only tool metadata exposed through `/api/tools`. | `backend/app/api/tools.py`, `backend/app/agents/tool_catalog/server_declared.py` |
| Runtime tool | A granted executable tool exposed to workflow agents at runtime. | `backend/app/agents/runtime_tools/registry.py` |
| Package secret binding | An encrypted package-local secret value keyed by package and binding key. | `backend/app/models/workflow_package.py`, `backend/app/schemas/workflow_package.py` |
| Explicit-scope memory | Platform-core memory constrained by package context and a concrete private scope. | `backend/app/api/memory.py`, `backend/app/schemas/memory.py` |
| Report source | Canonical report origin value: `compiled`, `uploaded`, `external`, or `agent`. | `backend/app/models/report.py`, `backend/app/schemas/report.py` |

## 5. Functional Requirements

All functional requirements below are stated only when the implementation provides direct code and/or test support. Inferred product ideas that were not promoted to confirmed requirements were moved to Sections 12 and 15.

### FR-001: Portfolio Workspaces

Statement:
The system MUST allow clients to create, list, read, update, and delete portfolio workspaces identified by unique slugs. Portfolio reads MUST expose portfolio-scoped summary counts.

Rationale:
Portfolios are the root finance workspace container used by balances, positions, trading operations, and market-data reads.

Evidence:
- `backend/app/api/portfolios.py` :: `list_portfolios`, `create_portfolio`, `get_portfolio`, `update_portfolio`, `delete_portfolio` — exposes `/api/v1/portfolios` CRUD.
- `backend/app/schemas/portfolio.py` :: `PortfolioCreate`, `PortfolioUpdate`, `PortfolioRead` — enforces slug format and omits slug from update payloads.
- `backend/tests/test_api.py` :: `test_portfolio_isolation_and_summary_counts`, `test_portfolio_slug_validation_uniqueness_and_immutability` — proves isolation, counts, uniqueness, and immutability.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a valid name and slug, when a client POSTs to `/api/v1/portfolios`, then a portfolio record is created and returned.
- Given an existing portfolio, when a client PATCHes mutable fields, then name and/or description update without slug mutation.
- Given multiple portfolios, when a client lists portfolios, then each row reports portfolio-scoped balance and position counts.

Edge Cases:
- Invalid slug format is rejected.
- Duplicate slugs are rejected.

### FR-002: Balance Management

Statement:
The system MUST manage portfolio-scoped balance rows with non-negative amounts and an operation type, and it MUST allow create, list, update, and delete behavior under a portfolio.

Rationale:
Balances are the cash substrate for trading simulations and finance analytics.

Evidence:
- `backend/app/api/balances.py` :: `list_balances`, `create_balance`, `update_balance`, `delete_balance` — exposes nested CRUD under `/api/v1/portfolios/{portfolioId}/balances`.
- `backend/app/models/balance.py` :: `Balance` — constrains non-negative `amount` and unique `(portfolio_id, label)`.
- `backend/tests/test_api.py` :: `test_balance_crud` — proves CRUD behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a portfolio, when the client creates a balance, then the response returns the created balance under that portfolio.
- Given an existing balance, when the client PATCHes mutable fields, then the updated record is returned.
- Given an existing balance, when the client DELETEs it, then the route returns success with no body.

Edge Cases:
- Duplicate balance labels inside one portfolio are rejected.
- Negative amounts are rejected.

### FR-003: Positions And CSV Import

Statement:
The system MUST manage portfolio-scoped positions, MUST support provider-assisted symbol lookup, and MUST support a preview/commit CSV import flow for positions.

Rationale:
Positions are the canonical holdings representation and the import flow is a first-class data-entry path.

Evidence:
- `backend/app/api/positions.py` :: `list_positions`, `create_position`, `lookup_position_symbol`, `preview_position_import`, `commit_position_import`, `update_position`, `delete_position` — exposes nested position routes and import endpoints.
- `backend/app/models/position.py` :: `Position` — constrains positive quantity, non-negative average cost, and unique `(portfolio_id, symbol)`.
- `backend/tests/test_api.py` :: `test_position_crud`, `test_csv_preview_and_commit_flow`, `test_position_symbol_lookup_returns_provider_name_and_uses_cache` — proves CRUD, import, and lookup/cache behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a portfolio, when the client POSTs a valid position, then the position is created under that portfolio.
- Given a CSV file, when the client calls preview, then row-level validation details are returned without persistence.
- Given a valid previewable CSV, when the client commits it, then position rows are created or updated for that portfolio.

Edge Cases:
- Missing provider name lookup does not block manual position creation.
- Import validation failures block commit.

### FR-004: Trading Operation Simulation

Statement:
The system MUST support simulated `BUY`, `SELL`, `DIVIDEND`, and `SPLIT` trading operations and MUST update linked balance and position state deterministically.

Rationale:
Trading operations are the implementation's finance simulation engine.

Evidence:
- `backend/app/api/trading_operations.py` :: `list_trading_operations`, `create_trading_operation` — exposes `/api/v1/portfolios/{portfolioId}/trading-operations`.
- `backend/app/extensions/signaldeck_finance/services/trading_operation_service.py` :: `create_operation`, `_apply_buy`, `_apply_sell`, `_apply_split` — implements side-specific business rules.
- `backend/tests/test_api.py` :: `test_trading_operations_respect_withdrawals_and_deposit_balances`, `test_dividend_requires_existing_position`, `test_split_requires_existing_position`, `test_split_succeeds_without_balance`, `test_trade_linked_balance_cannot_change_operation_type` — proves operation constraints and state updates.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a deposit balance and sufficient cash, when the client submits `BUY`, then the balance decreases and the position is created or updated.
- Given an existing position, when the client submits `SELL`, then the balance increases and the position quantity decreases or the aggregate row is removed at full sell-down.
- Given an existing position, when the client submits `DIVIDEND` or `SPLIT`, then the corresponding balance or position mutation is applied.

Edge Cases:
- Oversell attempts are rejected.
- Dividend and split operations on non-existent positions are rejected.

### FR-005: Market Data And Degraded Fallback

Statement:
The system MUST expose quote and history reads for portfolio symbols and SHOULD degrade to cached data or warnings rather than making local portfolio data unusable when providers fail.

Rationale:
The implementation treats local persistence as authoritative even when external providers are unavailable.

Evidence:
- `backend/app/api/market_data.py` :: `get_quotes`, `get_history` — exposes `/api/v1/portfolios/{portfolioId}/market-data/quotes` and `/history`.
- `backend/app/models/market_quote.py` :: `MarketQuote` — persists rebuildable quote cache rows.
- `backend/tests/test_api.py` :: `test_market_data_falls_back_to_cached_quote`, `test_market_data_recomputes_cached_quote_staleness_on_fallback`, `test_market_data_history_returns_multiple_series` — proves fallback and history behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given tracked symbols, when a client requests quotes, then quote rows are returned with provider-normalized fields.
- Given provider failure and cached quotes, when a client requests quotes, then cached quotes are returned with degraded-state signaling.
- Given requested symbols and time ranges, when a client requests history, then multiple series may be returned.

Edge Cases:
- Cached quotes may be marked stale on fallback.
- Provider failure does not imply portfolio deletion or position invalidation.

### FR-006: Templates And Placeholder Compilation

Statement:
The system MUST support reusable text templates, MUST compile templates against runtime inputs, and MUST expose a placeholder tree rooted at `inputs`, `portfolios`, and `reports`.

Rationale:
Templates are a first-class authoring surface and a prerequisite for report generation.

Evidence:
- `backend/app/api/templates.py` :: CRUD, inline compile, stored compile, and placeholder routes.
- `backend/app/extensions/signaldeck_finance/services/template_compiler_service.py` :: `compile`, `get_placeholder_tree` — resolves `inputs`, `portfolios`, and `reports` placeholders.
- `backend/tests/test_api.py` :: `test_template_crud_and_compile_flow`, `test_template_compile_accepts_runtime_inputs`, `test_template_compile_surfaces_missing_runtime_inputs`, `test_placeholder_tree_includes_reports` — proves compile and placeholder behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a stored template, when a client requests compile with runtime inputs, then compiled content is returned.
- Given inline content, when a client calls inline compile, then the compiled result is returned without creating a template.
- Given placeholder browsing, when a client requests `/api/v1/templates/placeholders`, then portfolio and report trees are returned.

Edge Cases:
- Missing runtime input values surface compile errors or missing markers.
- Dynamic portfolio/report selectors may resolve to empty output rather than crash.

### FR-007: Reports Lifecycle And Slug-Addressed Access

Statement:
The system MUST support compiled, uploaded, external, and server-origin agent report records; report reads, updates, deletes, and downloads MUST be slug-addressed after creation, and public JSON report creation MUST remain external-only.

Rationale:
Reports are durable markdown snapshots and one of the main user-facing artifacts.

Evidence:
- `backend/app/api/reports.py` :: list/create/compile/upload/get/update/delete/download routes.
- `backend/app/models/report.py` and `backend/app/schemas/report.py` :: canonical `source` values, slug uniqueness, metadata handling, and immutable API-level name/slug/source behavior.
- `backend/tests/test_api.py` :: `test_report_compile_crud_and_download`, `test_report_upload_crud_and_download`, `test_report_create_external_json`, `test_report_source_filter_accepts_agent`, `test_public_report_create_rejects_agent_created_by_provenance` — proves route contracts and provenance rules.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a compiled template result, when the client creates a compiled report, then a new report snapshot is stored with `source="compiled"`.
- Given uploaded markdown, when the client posts multipart upload, then an uploaded report is stored and later downloadable by slug.
- Given an existing report slug, when the client reads, patches content, deletes, or downloads, then the route resolves by slug.

Edge Cases:
- `external` is limited to true external user/API-created reports.
- Public clients cannot supply server-owned agent provenance for non-agent reports.
- No automatic report expiration or cleanup contract is evidenced; report records are removed only by explicit delete paths, including report deletion by slug and run deletion for run-owned agent-memory report rows.

### FR-008: Workflow Package Manifest Authoring

Statement:
The system MUST treat Workflow Packages as the only live executable workflow authoring root and MUST validate package manifests before or during save/import.

Rationale:
Workflow Packages replace older global authoring surfaces and are the core platform artifact.

Evidence:
- `backend/app/api/workflow_packages.py` :: create, update, validate, import, export, manifest, launch routes.
- `backend/app/services/workflow_package_manifest_parser.py` :: rejects aliases, anchors, merge keys, unsupported tags, non-finite numbers, forbidden keys, and `spec.skills`.
- `backend/tests/test_workflow_package_preflight.py`, `backend/tests/test_workflow_package_api.py`, `frontend/src/pages/workflow-packages/*.test.tsx` — prove package-first authoring, validation, and removed status/version query behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given valid manifest YAML, when a client validates or saves it, then the API returns parsed metadata and/or a persisted package artifact.
- Given invalid manifest YAML or unsupported features, when the client validates or saves it, then diagnostics are returned and persistence is blocked.
- Given an existing package, when the client exports its manifest, then the export reflects package-local resources instead of global authoring rows.

Edge Cases:
- `spec.skills` is rejected in favor of capability profiles.
- Raw ids and forbidden secret-like keys are rejected.
- Import/export is a current-contract artifact flow; removed version/status selection and long-term backward-compatibility guarantees are not part of the live contract.

### FR-009: Package Secret Bindings And HTTP Operation Nodes

Statement:
The system MUST support package-local encrypted secret bindings and MUST restrict package HTTP operation nodes to allowed request fields, methods, and runtime safety rules.

Rationale:
HTTP operations are a shipped non-agent workflow capability and depend on package-local secret storage.

Evidence:
- `backend/app/api/workflow_packages.py` :: secret binding list/upsert/delete routes.
- `backend/app/schemas/workflow_package.py` :: `WorkflowPackageSecretBindingRead` and `WorkflowPackageSecretBindingUpdateRequest` — secret-safe read/write contract.
- `backend/app/services/workflow_package_manifest_parser.py` and `backend/app/services/http_operation_execution_service.py` — enforce secret-ref placement and HTTP request/response safety.
- `backend/tests/test_workflow_package_manifest_http_node.py`, `backend/tests/test_http_operation_execution_service.py`, `backend/tests/test_workflow_package_run_contracts.py` — prove secret refs, SSRF/redirect/size/content-type controls, and secret-safe provenance.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a package id and binding key, when the client writes a secret binding, then the API stores it without echoing the raw value in reads.
- Given a package HTTP node, when it references `${{ secrets.key }}` outside `url`, `headers`, `query`, or `body`, then validation rejects it.
- Given an HTTP operation run, when the runtime dispatches it, then method, timeout, redirect, network, and output-schema checks are enforced before returning success.

Edge Cases:
- Unsupported HTTP methods are rejected.
- Oversize bodies, unsupported content types, invalid JSON, and redirect/private-network violations fail closed.

### FR-010: Launch Metadata, Runtime Inputs, And Saved Inputs

Statement:
The system MUST expose a dedicated launch metadata/preflight/create-run flow outside the package editor and MUST validate runtime inputs against the selected workflow input schema.

Rationale:
The implementation separates authoring from execution and treats launch state as a dedicated surface.

Evidence:
- `backend/app/api/workflow_packages.py` :: `preflight_workflow_package`, `get_workflow_package_launch`, `create_workflow_package_launch`, runtime-input-registry routes.
- `backend/app/schemas/workflow_package.py` :: launch, preflight, and runtime-input-registry DTOs.
- `backend/tests/test_workflow_package_run_contracts.py` :: rerun/fork/runtime-input payload semantics.
- `frontend/src/pages/workflow-packages/launch.test.tsx` :: proves generated schema inputs, raw JSON fallback, defaults, omitted optional fields, and validation feedback.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a package and workflow, when the client requests launch metadata, then the API returns readiness, warnings, and the workflow input schema.
- Given launch parameters, when the client preflights or launches, then the payload is validated against the workflow input schema.
- Given saved runtime input presets, when the client creates, updates, lists, or deletes them for one package workflow, then the registry behavior stays workflow-scoped.
- Given saved inputs whose manifest, compiled plan, or schema fingerprint no longer matches the current workflow, when the registry is read, then stale status is exposed rather than silently rewriting the payload.

Edge Cases:
- Unsupported or non-object raw JSON is rejected before launch.
- Structured generated-form support applies only to the currently supported object-schema subset; unsupported schemas remain on raw JSON fallback instead of implying broader structured-editor support.
- Optional fields without defaults may remain absent rather than materializing as null.
- Saved runtime input presets are bounded per package/workflow scope and history entries are trimmed rather than growing without limit.

### FR-011: Scheduled Tasks

Statement:
The system MUST allow users to create, list, update, preview, run now, inspect fire history for, and delete Scheduled Tasks that target one current Workflow Package workflow.

Rationale:
Scheduled Tasks are the package-first automation surface for recurring runs.

Evidence:
- `backend/app/api/schedules.py` :: list/create/get/update/delete/preview/run-now/fire-history routes.
- `backend/app/schemas/schedule.py` :: structured recurrence, IANA timezone validation, preview, run-now, and fire DTOs.
- `backend/app/services/workflow_package_schedule_inputs.py` :: placeholder allowlist and render-validation rules.
- `backend/tests/test_workflow_package_preflight.py`, `backend/tests/test_workflow_package_run_contracts.py`, `frontend/e2e/scheduled-tasks.spec.ts` — prove recurrence, preview, run-now, fire history, deletion, and schedule provenance behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given schedule create data, when the client POSTs to `/api/schedules`, then the API stores one schedule tied to one package and workflow.
- Given a stored or unsaved schedule, when the client previews it, then rendered parameters and validation errors are returned without creating a run.
- Given a valid schedule and idempotency key, when the client runs it now, then a manual fire and linked queued run are created and returned.
- Given a stored schedule detail read, when the client fetches it, then the response omits the editable `inputTemplate` and `templateVars` fields that are only present on write/preview flows.

Edge Cases:
- Only structured recurrence types are accepted; raw cron is not evidenced.
- Unsupported placeholder expressions or missing placeholder values block ready previews.
- Paused schedules may still use run-now, and repeated run-now requests with the same schedule, scheduled time, and idempotency key return the same fire/run pair.
- DST, overlap, and misfire behavior are backend-owned materialization rules rather than client-side calculations.

### FR-012: Model Connections

Statement:
The system MUST manage global model endpoint bindings with writable `protocolProfile`, write-only secret updates, backend-owned compatibility/probe data, and secret-safe reads.

Rationale:
Model Connections are the live provider/runtime binding used by packages at preflight, launch, and execution time.

Evidence:
- `backend/app/api/model_connections.py` :: list/create/get/update/delete/connection-test/capability-probe routes.
- `backend/app/schemas/model_connection.py` :: protocol profile, base URL, key, apiKey, capability probe, and compatibility resolution contracts.
- `backend/tests/test_api.py` :: `test_model_connection_compatibility_derives_caps_and_rejects_public_policy_writes`, `test_model_connection_rejects_invalid_protocol_profile`, `test_model_connection_connection_test_uses_provider_openai_behavior` — proves write restrictions and probe/test behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a valid connection payload, when the client creates or updates a model connection, then writable identity and endpoint settings persist.
- Given a saved connection, when the client requests a read payload, then raw secrets are not returned.
- Given a saved connection, when the client runs a connection test or capability probe, then the API returns backend-owned result metadata.

Edge Cases:
- Empty or null API key updates are rejected.
- Unsupported or mismatched protocol compatibility values are rejected.
- Deleting a model connection removes the saved row but does not cascade current packages or historical run snapshots that still reference the key; later readiness checks surface the missing binding.

### FR-013: Extensions And Extension-Gated Surfaces

Statement:
The system MUST expose bundled extension state only as `{key, label, enabled}` and MUST gate finance-owned routes and tools through the enabled state.

Rationale:
Bundled extension state is the core platform boundary for what surfaces are visible or executable.

Evidence:
- `backend/app/api/extensions.py` and `backend/app/services/extension_service.py` — public extension list/toggle contract and enabled-state filtering.
- `backend/app/extensions/registry.py` — bundled finance and digital_oracle registry wiring and default-enabled state.
- `frontend/src/extensions/runtime-helpers.ts`, `frontend/src/extensions/signaldeck-finance/scaffold.ts`, `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts` — route/nav/tool filtering and Digital Oracle tool-only behavior.
- `backend/tests/test_extensions_api.py`, `backend/tests/test_extension_lifecycle_matrix.py`, `frontend/e2e/extensions.spec.ts` — prove slim state and lifecycle independence.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given `/api/extensions`, when the client reads extension state, then only `key`, `label`, and `enabled` are returned.
- Given `signaldeck.finance` disabled, when the user visits finance-owned routes or requests finance-owned tools, then those surfaces are blocked or hidden.
- Given `signaldeck.digital_oracle`, when the system renders navigation, then no Digital Oracle route or nav item is added.

Edge Cases:
- Digital Oracle tool visibility is independent from finance visibility.
- Default-enabled bundled extensions may still be toggled off and back on.

### FR-014: Server-Declared Tools And Extension Filtering

Statement:
The system MUST expose a read-only server-declared tool catalog at `/api/tools`, and extension-owned tools MUST be filtered by enabled extension state while platform-core memory tools remain visible.

Rationale:
Tool discovery is intentionally metadata-only in the browser/API surface and separate from runtime dispatch.

Evidence:
- `backend/app/api/tools.py` :: `list_tools` — exposes only `key`, `displayName`, and `description`.
- `backend/app/agents/tool_catalog/server_declared.py` and `backend/app/agents/runtime_tools/registry.py` — define core memory tools plus extension-filtered visibility and dispatch.
- `backend/tests/test_tool_catalog_api.py`, `backend/tests/test_runtime_tools.py`, `frontend/src/hooks/use-workflow-packages.test.ts` — prove extension filtering and stable tool ownership.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a tools catalog request, when the client GETs `/api/tools`, then the response contains read-only tool metadata only.
- Given disabled extension-owned tools, when the catalog is rendered or filtered for package authoring, then disabled tool keys are hidden.
- Given both bundled extensions disabled, when the tools catalog is read, then platform-core memory tools still remain visible.

Edge Cases:
- Duplicate or unknown tool keys are rejected during package validation rather than silently accepted.
- Deferred Digital Oracle candidates are not exposed as shipped catalog entries.

### FR-015: Launch Queueing, Runs, Reruns, And Forks

Statement:
The system MUST queue launches as global runs, MUST expose run list/detail evidence, and MUST support rerun and fork descendant flows with preserved lineage and package provenance.

Rationale:
Runs are the main execution monitor and audit surface for package-based workflows.

Evidence:
- `backend/app/api/runs.py` :: list/get/delete/rerun-draft/reruns/fork-draft/forks routes.
- `backend/app/schemas/run.py` :: run list/detail, progress, queue, schedule provenance, rerun, and fork DTOs.
- `backend/app/workers/run_scheduler.py` :: explicit scheduler worker that materializes due schedules, claims queued runs, heartbeats leases, and executes claimed runs.
- `backend/tests/test_workflow_package_run_contracts.py`, `backend/tests/test_runtime_repositories.py`, `frontend/src/pages/runs/detail.test.tsx`, `frontend/e2e/runs.spec.ts` — prove provenance, queueing, rerun, fork, and detail rendering.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a valid launch request, when the client creates a launch, then the API returns a queued run instead of executing inline.
- Given an existing run, when the client requests run detail, then execution evidence, package provenance, progress, queue state, and memory evidence are returned.
- Given an existing run, when the client creates a rerun or fork, then a descendant queued run is created with preserved lineage.

Edge Cases:
- Runs reject deprecated `targetKind`/`targetId`/`targetKey` list filters.
- Fork targets are limited to supported agent invocation inputs, not arbitrary operation rows.
- `DELETE /api/runs/{runId}` is a live operator-facing API feature that hard-deletes the targeted run, removes its run-owned agent-memory report rows, and preserves descendant runs by nulling lineage references instead of deleting descendants.

### FR-016: Platform-Core Memory

Statement:
The system MUST expose platform-core memory only through explicit package context and concrete private scopes, and it MUST keep canonical memory separate from report-domain history.

Rationale:
Memory is implemented as a scoped platform capability rather than as generic global CRUD.

Evidence:
- `backend/app/api/memory.py` :: list/detail/revisions/events/resolve/reflect routes under `/api/memory`.
- `backend/app/schemas/memory.py` :: explicit-scope request models, namespace grants, opaque `memoryId`, and projection limits.
- `backend/tests/test_memory_service.py`, `backend/tests/test_memory_domain_schemas.py`, `backend/tests/test_memory_layer_static_contracts.py`, `frontend/e2e/memory.spec.ts` — prove scoped lookup, grants, memory/report separation, and browser gating.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given a package access context and explicit private scope, when the client queries memory, then bounded memory projections are returned.
- Given a valid memory id and access context, when the client loads detail, revisions, events, resolve, or reflect flows, then the API authorizes against the stored scope.
- Given runtime memory writes, when duplicate active content is written, then the implementation may reuse the existing active revision rather than create a conflicting duplicate.

Edge Cases:
- Unscoped global memory search is not evidenced as a live path.
- Namespace access without explicit grants is denied.

### FR-017: Workflow Packages As The Authoring Surface

Statement:
The system MUST expose Workflow Packages as the authoring entry point for executable agent workflows.

Rationale:
The implementation routes executable authoring through package manifests and treats retired global authoring as non-goal scope.

Evidence:
- `backend/app/api/workflow_packages.py` :: package authoring API routes.
- `backend/tests/test_workflow_package_api.py` :: package create/import/export/read behavior.
- `frontend/src/routes.test.tsx` :: the package route and product-owned unknown-route shell are covered.
- `README.md`, `docs/prd.md`, `docs/spec.md` — explicitly describe Workflow Packages as the only live authoring root.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given live authoring needs, when the user uses the product, then Workflow Packages are the entry point.
- Given a package manifest, when it is imported or edited, then package-local agents, workflows, output schemas, capability profiles, and MCP config stay inside the package artifact.
- Given an unsupported browser route, when a user navigates to it, then the app renders the shell-owned not-found route.

Edge Cases:
- Retired global authoring remains documented only as non-goal scope, not as a compatibility alias.
- Schema repair must not reintroduce retired global authoring persistence as a live authoring path.

### FR-018: API Contract Conventions And Shared Error Behavior

Statement:
The system MUST use camelCase external JSON fields, string-serialized decimals, UTC timestamps, and a shared error envelope of `{code, message, details[]}`.

Rationale:
These conventions are cross-cutting API contracts relied on by the frontend and tests.

Evidence:
- `backend/app/main.py` :: `api_error_handler`, `request_validation_handler`, `/health`, `/ready` — centralizes shared error behavior and validation-error shape.
- `docs/spec.md` :: API conventions section — corroborates camelCase, decimal strings, timestamps, and error envelopes.
- `backend/tests/test_api.py` :: `test_browser_safe_error_details_preserve_public_scalars_and_drop_unsafe_values`, `test_api_error_envelope_details_are_browser_safe` — proves error-envelope behavior.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given domain or business-rule failures, when the API returns an error, then the payload includes `code`, `message`, and `details`.
- Given validation failures, when the framework or handler rejects the request, then the payload uses the validation-error contract.
- Given decimal money/quantity values or timestamps, when the API serializes responses, then it preserves the shared wire conventions.

Edge Cases:
- Browser-safe error shaping may redact unsafe values from `details`.
- Readiness differs from liveness and may return unavailable when PostgreSQL cannot be reached.

### FR-019: Dashboard Landing Contract

Statement:
The system MUST expose a finance-gated dashboard landing route with a stable `Dashboard` title, `Portfolio overview.` description, consistent route identity across loading and ready states, and a retryable API-error state. The current contract MUST NOT imply summary cards, charts, or richer metrics beyond that evidenced landing behavior.

Rationale:
The dashboard is a live shipped route, but its tested behavior is intentionally narrow and should not be overstated.

Evidence:
- `frontend/src/pages/dashboard.tsx` :: `Dashboard` — renders a stable header plus a retryable error panel and no summary-card logic.
- `frontend/src/pages/dashboard.test.tsx` :: `renders the normalized dashboard hero without summary cards`, `keeps the same dashboard identity while loading`, `renders stable dashboard retry behavior for API errors` — proves the current browser contract.
- `frontend/src/extensions/signaldeck-finance/scaffold.ts` :: finance-owned dashboard route contribution and metadata.

Confidence:
High

Status:
Confirmed

Acceptance Criteria:
- Given the finance workspace is enabled, when the user opens `/`, then the app renders the `Dashboard` heading and `Portfolio overview.` description.
- Given portfolio data is still loading, when the route renders, then the same dashboard identity remains visible.
- Given the portfolio query fails, when the route renders, then the user sees a retryable error state for the dashboard summary.

Edge Cases:
- Dashboard route visibility is gated by the finance extension state.
- No summary-card, chart, or metric-band promise is part of the confirmed contract unless implemented later.

## 6. User Journeys / Use Cases

### UJ-001: Manage A Portfolio
- Actor: Trusted operator
- Goal: Maintain a portfolio and its balances/positions.
- Preconditions: `signaldeck.finance` is enabled.
- Main flow: create portfolio -> create balances/positions -> inspect counts and market context.
- Alternative flows: import positions from CSV; create manual positions without provider name lookup.
- Failure flows: invalid slug, duplicate slug, invalid import rows, disabled finance extension.
- Evidence: `backend/app/api/portfolios.py`, `backend/app/api/positions.py`, `backend/tests/test_api.py`.

### UJ-002: Compile A Template Into A Report
- Actor: Trusted operator
- Goal: Reuse a template with runtime inputs and persist the output as a report.
- Preconditions: Finance extension enabled; required runtime inputs are available.
- Main flow: create/edit template -> preview or stored compile -> generate report.
- Alternative flows: use latest report selectors or portfolio selectors inside placeholders.
- Failure flows: missing input values, placeholder cycles, provider degradation for market-dependent placeholders.
- Evidence: `backend/app/extensions/signaldeck_finance/services/template_compiler_service.py`, `backend/tests/test_api.py`.

### UJ-003: Upload Or Manage Reports
- Actor: Trusted operator
- Goal: Persist and review markdown reports by slug.
- Preconditions: Finance extension enabled.
- Main flow: upload or create external report -> list/filter -> open detail -> edit content -> download or delete.
- Alternative flows: compiled or agent-origin reports appear in the same list surface.
- Failure flows: slug conflicts, invalid upload, invalid external provenance, not found slug.
- Evidence: `backend/app/api/reports.py`, `frontend/e2e/reports.spec.ts`.

### UJ-004: Author And Validate A Workflow Package
- Actor: Workflow package author
- Goal: Create a package-local workflow artifact without using deprecated global authoring.
- Preconditions: Platform routes available.
- Main flow: edit manifest/resources -> validate -> save/import -> review package detail/export.
- Alternative flows: manage package-local secret bindings and saved runtime input presets.
- Failure flows: malformed YAML, unsupported manifest features, unresolved dependencies, disabled extension/tool references.
- Evidence: `backend/app/api/workflow_packages.py`, `backend/app/services/workflow_package_manifest_parser.py`, `frontend/src/pages/workflow-packages/*.test.tsx`.

### UJ-005: Launch A Workflow Package
- Actor: Workflow package author or operator
- Goal: Queue a run from a saved package workflow.
- Preconditions: Package exists; selected workflow is launchable.
- Main flow: read launch metadata -> preflight with parameters -> create queued run -> navigate to run detail.
- Alternative flows: use saved runtime input presets or raw JSON entry mode.
- Failure flows: non-object JSON, readiness blockers, missing secret bindings, failed or missing model connection.
- Evidence: `backend/app/api/workflow_packages.py`, `frontend/src/pages/workflow-packages/launch.test.tsx`.

### UJ-006: Schedule A Package Run
- Actor: Workflow package author or operator
- Goal: Recursively run one workflow on a structured recurrence.
- Preconditions: Package and workflow exist.
- Main flow: create schedule -> preview rendered parameters -> save -> inspect fire history -> run now -> follow linked run.
- Alternative flows: pause/resume and edit recurrence or template vars.
- Failure flows: invalid timezone, unsupported placeholders, schema-invalid rendered parameters, extension-disabled readiness failure.
- Evidence: `backend/app/api/schedules.py`, `backend/app/services/workflow_package_schedule_inputs.py`, `frontend/e2e/scheduled-tasks.spec.ts`.

### UJ-007: Inspect And Descend From A Run
- Actor: Workflow package author or operator
- Goal: Inspect execution evidence and create descendants.
- Preconditions: Run exists.
- Main flow: list runs -> open run detail -> inspect outputs, steps, invocations, provenance, memory, and queue state.
- Alternative flows: create rerun from root parameters; create fork from one invocation input.
- Failure flows: unsupported fork target, readiness blockers, queued worker delay, not found run.
- Evidence: `backend/app/api/runs.py`, `backend/app/workers/run_scheduler.py`, `frontend/src/pages/runs/detail.test.tsx`.

### UJ-008: Inspect Explicit-Scope Memory
- Actor: Trusted operator with package context
- Goal: Review canonical memory entries for one explicit private scope.
- Preconditions: Package key and scope context are known.
- Main flow: choose package/workflow/agent/run context -> choose explicit private scope -> list memory -> open detail/revisions/events -> resolve or reflect.
- Alternative flows: filter by kind or status.
- Failure flows: missing package context, unauthorized namespace, invalid memory id.
- Evidence: `backend/app/api/memory.py`, `frontend/src/pages/memory/list.tsx`, `frontend/e2e/memory.spec.ts`.

## 7. API / Function Contract Requirements

The table below summarizes the public contract surfaces that are evidence-backed. Endpoint groups are listed explicitly to avoid inventing a hidden API.

| Surface | Public contract | Inputs / validation | Outputs / side effects | Auth / permission / notes | Evidence |
| --- | --- | --- | --- | --- | --- |
| Health and readiness | `GET /health`, `GET /ready` | none; readiness checks DB reachability | liveness/readiness JSON | no auth evidenced | `backend/app/main.py` |
| Portfolios | `GET/POST /api/v1/portfolios`, `GET/PATCH/DELETE /api/v1/portfolios/{portfolioId}` | typed create/update DTOs; create slug validation | CRUD over `portfolios` | finance extension gate | `backend/app/api/portfolios.py`, `backend/app/schemas/portfolio.py` |
| Balances | `GET/POST /api/v1/portfolios/{portfolioId}/balances`, `PATCH/DELETE .../{balanceId}` | balance DTO validation | CRUD over `balances` | finance extension gate | `backend/app/api/balances.py` |
| Positions | `GET/POST /api/v1/portfolios/{portfolioId}/positions`, `GET .../lookup`, `PATCH/DELETE .../{positionId}` | position DTOs and lookup params | CRUD plus provider/cache-assisted symbol lookup | finance extension gate | `backend/app/api/positions.py` |
| CSV import | `POST .../positions/imports/preview`, `POST .../positions/imports/commit` | uploaded CSV and validation | preview diagnostics or persisted upserts | finance extension gate | `backend/app/api/positions.py`, `backend/tests/test_api.py` |
| Trading operations | `GET/POST /api/v1/portfolios/{portfolioId}/trading-operations` | discriminated operation payloads | append operation row plus balance/position mutation | finance extension gate | `backend/app/api/trading_operations.py`, `backend/app/extensions/signaldeck_finance/services/trading_operation_service.py` |
| Market data | `GET .../market-data/quotes`, `GET .../market-data/history` | symbol/time-range queries | quote/history payloads with warnings/fallback | finance extension gate | `backend/app/api/market_data.py` |
| Templates | `GET/POST /api/v1/templates`, `GET/PATCH/DELETE /api/v1/templates/{templateId}`, `POST /api/v1/templates/compile`, `GET/POST /api/v1/templates/{templateId}/compile`, `GET /api/v1/templates/placeholders` | template DTOs and runtime input maps | CRUD, compile, placeholder browsing | finance extension gate | `backend/app/api/templates.py` |
| Reports | `GET/POST /api/v1/reports`, `POST /api/v1/reports/compile/{templateId}`, `POST /api/v1/reports/upload`, `GET/PATCH/DELETE /api/v1/reports/{slug}`, `GET /api/v1/reports/{slug}/download` | source-specific DTOs and multipart upload | report persistence, filtering, download | finance extension gate | `backend/app/api/reports.py` |
| Workflow packages | `GET/POST /api/workflow-packages`, `POST /api/workflow-packages/validate-manifest`, `POST /api/workflow-packages/import`, `GET/PATCH/DELETE /api/workflow-packages/{packageId}`, `GET /manifest`, `GET /export` | manifest source, import payloads, removed query guards | mutable current package artifact, validation diagnostics, export response | platform core | `backend/app/api/workflow_packages.py` |
| Package secret bindings | `GET /api/workflow-packages/{packageId}/secret-bindings`, `PUT/DELETE /api/workflow-packages/{packageId}/secret-bindings/{key}` | key plus write-only secret value | encrypted binding persistence | platform core | `backend/app/api/workflow_packages.py`, `backend/app/schemas/workflow_package.py` |
| Runtime input registry | `GET /api/workflow-packages/{packageId}/runtime-input-registry?workflowKey=...`, `POST/PATCH/DELETE .../presets/...` | workflow-scoped payloads | preset/history registry entries | platform core | `backend/app/api/workflow_packages.py` |
| Launch and preflight | `POST /api/workflow-packages/{packageId}/preflight`, `GET /api/workflow-packages/{packageId}/launch`, `POST /api/workflow-packages/{packageId}/launches` | workflow key and parameters | readiness summary or queued run | platform core | `backend/app/api/workflow_packages.py`, `backend/app/schemas/workflow_package.py` |
| Schedules | `GET/POST /api/schedules`, `POST /api/schedules/preview`, `GET/PATCH/DELETE /api/schedules/{scheduleId}`, `POST /api/schedules/{scheduleId}/preview`, `POST /api/schedules/{scheduleId}/run-now`, `GET /api/schedules/{scheduleId}/fires` | structured recurrence, IANA timezone, JSON templates, idempotency key | schedule records, previews, manual fire/run, fire history | platform core | `backend/app/api/schedules.py`, `backend/app/schemas/schedule.py` |
| Model connections | `GET/POST /api/model-connections`, `GET/PATCH/DELETE /api/model-connections/{connectionId}`, `POST /connection-test`, `POST /capability-probe` | validated key/baseUrl/modelId/protocolProfile/apiKey | CRUD plus connection test and capability metadata | platform core | `backend/app/api/model_connections.py`, `backend/app/schemas/model_connection.py` |
| Extensions | `GET /api/extensions`, `PATCH /api/extensions/{extensionKey}` | `enabled` toggle only | slim extension state | platform core | `backend/app/api/extensions.py` |
| Tools | `GET /api/tools` | none | read-only `{key,displayName,description}` list | platform core; extension-filtered | `backend/app/api/tools.py` |
| Memory | `POST /api/memory`, `POST /api/memory/{memoryId}/detail`, `POST /revisions`, `POST /events`, `POST /actions/resolve`, `POST /actions/reflect` | accessContext plus explicit-scope body payloads | bounded scoped memory projections and status actions | platform core; scope- and grant-aware | `backend/app/api/memory.py`, `backend/app/schemas/memory.py` |
| Runs | `GET /api/runs`, `GET/DELETE /api/runs/{runId}`, `GET /api/runs/{runId}/rerun-draft`, `POST /api/runs/{runId}/reruns`, `GET /api/runs/{runId}/fork-draft?sourceInvocationId=...`, `POST /api/runs/{runId}/forks` | list filters, rerun params, fork invocation input | run reads, descendant queued runs, hard delete | platform core | `backend/app/api/runs.py`, `backend/app/schemas/run.py` |
| Scheduler worker job | `python -m app.workers.run_scheduler` | runtime settings and DB access | materializes due schedules, claims queued runs, executes and heartbeats them | internal runtime actor | `backend/app/workers/run_scheduler.py` |
| Local startup helper | `./start.sh` | local env and optional cleanup flag | starts db/backend/frontend/scheduler with fallback ports | developer/operator utility | `README.md` |

## 8. Data Requirements

### Entities, Fields, Relationships, And Constraints

| Entity | Key fields / relationships | Constraints / lifecycle evidence |
| --- | --- | --- |
| `portfolios` | `id`, `name`, `slug`, `description`; owns balances, positions, trading operations | unique slug; cascades to owned finance rows | 
| `balances` | `portfolio_id`, `label`, `operation_type`, `amount`, `currency` | unique `(portfolio_id,label)`; non-negative amount |
| `positions` | `portfolio_id`, `symbol`, `name`, `quantity`, `average_cost`, `currency`, `last_source` | unique `(portfolio_id,symbol)`; positive quantity; non-negative average cost |
| `trading_operations` | linked to portfolio and optional balance; stores side-specific fields | append-only history; supported sides are `BUY`, `SELL`, `DIVIDEND`, `SPLIT` |
| `market_quotes` | provider/symbol/as_of cache rows | rebuildable cache; stale flag persisted |
| `text_templates` | `name`, `content` | unique template name |
| `reports` | `name`, `slug`, `source`, `content`, `metadata` | unique name and slug; source constrained to `compiled`, `uploaded`, `external`, `agent` |
| `workflow_packages` | current mutable package artifact with `manifest_source`, hashes, compiled plan, dependency keys | no live status lifecycle is evidenced |
| `workflow_package_secret_bindings` | package-local encrypted `key` + `secret_payload` | unique per package+key; never exported in raw form |
| `workflow_package_runtime_input_entries` | workflow-scoped preset/history payloads | slot constrained to `history` or `preset`; tied to schema fingerprint and hashes |
| `workflow_package_schedules` | package/workflow target, recurrence, timezone, next fire, input template | status `enabled`/`paused`; overlap/misfire policies constrained |
| `workflow_package_schedule_fires` | schedule-owned fire rows with status, reason, scheduled fields, rendered parameters, linked run ids | deleted with owning schedule; not a preserved live surface after deletion |
| `model_connections` | global endpoint/model settings plus encrypted secret payload and compatibility metadata | protocol profile constrained; positive TTL/timeout; backend-owned capability/policy columns |
| `extension_states` | `extension_key`, `enabled` | canonical slim persisted extension state |
| `runs` | global package execution rows with queue state, progress, tokens, trace ids, schedule provenance | package-owned runs deleted with package; rerun/fork lineage retained separately |
| `run_forks` | one row per descendant fork run with source run/invocation and `resume_step_index` | fork lineage is explicit and first-class |
| `run_steps`, `run_agent_invocations`, `run_operation_invocations` | per-step, per-agent, and per-operation execution evidence | typed status fields, timestamps, graph metadata, redacted request/response metadata |
| `agent_memory_entries`, `agent_memory_revisions`, `run_memory_events` | canonical memory store and run-scoped memory evidence | opaque ids, immutable revisions, explicit-scope semantics |

### Persistence Rules

- Startup database initialization imports models, validates PostgreSQL support, creates tables, and runs in-code upgrade/repair logic via `backend/app/db/session.py` and `backend/app/db/upgrades.py`.
- The upgrade path explicitly repairs extension state, schedules, runs, memory, and removed legacy tables; Alembic is not the live authority.
- Schedule deletion preserves direct run history through run-owned `scheduleProvenance` while removing schedule-owned fire rows.
- Workflow Package deletion deletes owned runs; model-connection reads remain secret-safe and package exports omit raw secret values.

## 9. Business Rules

- **BR-001**: Portfolio slugs are lowercase identifiers, unique, and immutable after creation. Evidence: `backend/app/schemas/portfolio.py`, `backend/tests/test_api.py::test_portfolio_slug_validation_uniqueness_and_immutability`. Confidence: High.
- **BR-002**: Balance labels are unique within one portfolio and balance amounts cannot be negative. Evidence: `backend/app/models/balance.py`. Confidence: High.
- **BR-003**: Trading operations require deposit balances for buy/sell/dividend flows, and oversells are rejected. Evidence: `backend/app/extensions/signaldeck_finance/services/trading_operation_service.py`, `backend/tests/test_api.py`. Confidence: High.
- **BR-004**: Dividend and split operations require an existing position; split may succeed without an attached balance row. Evidence: `backend/tests/test_api.py::test_dividend_requires_existing_position`, `test_split_requires_existing_position`, `test_split_succeeds_without_balance`. Confidence: High.
- **BR-005**: Position CSV import uses preview before commit and commit applies validated rows to the target portfolio. Evidence: `backend/app/api/positions.py`, `backend/tests/test_api.py::test_csv_preview_and_commit_flow`. Confidence: High.
- **BR-006**: Quote/history degradation is warning-oriented and may fall back to cached rows instead of failing the local portfolio surface. Evidence: `backend/tests/test_api.py::test_market_data_falls_back_to_cached_quote`. Confidence: High.
- **BR-007**: Template placeholder roots are limited to `inputs`, `portfolios`, and `reports`; report and portfolio dynamic selectors are supported. Evidence: `backend/app/extensions/signaldeck_finance/services/template_compiler_service.py`, `backend/tests/test_api.py`. Confidence: High.
- **BR-008**: Public report creation may use `source="external"` only; server-owned agent provenance is rejected for non-agent reports. Evidence: `backend/app/schemas/report.py`, `backend/tests/test_api.py::test_public_report_create_rejects_agent_created_by_provenance`. Confidence: High.
- **BR-009**: Workflow package manifests reject YAML aliases, anchors, merge keys, unsupported tags, non-finite numbers, forbidden secret/id keys, and `spec.skills`. Evidence: `backend/app/services/workflow_package_manifest_parser.py`, `backend/tests/test_workflow_package_api.py`, `backend/tests/test_workflow_package_preflight.py`. Confidence: High.
- **BR-010**: Secret refs are valid only in HTTP request `url`, `headers`, `query`, and `body` fields. Evidence: `backend/app/services/workflow_package_manifest_parser.py`, `backend/tests/test_workflow_package_manifest_http_node.py`. Confidence: High.
- **BR-011**: Scheduled input placeholders are allowlisted to `schedule`, `fire`, `window`, `lastRun`, and `vars`. Evidence: `backend/app/services/workflow_package_schedule_inputs.py`, `frontend/src/pages/scheduled-tasks/detail.tsx`. Confidence: High.
- **BR-012**: Memory lookup is scoped; omitted runtime selectors fall back to current context instead of global search. Evidence: `backend/app/schemas/memory.py`, `backend/tests/test_memory_domain_schemas.py::test_memory_query_defaults_to_current_context_fallback_and_budgets`. Confidence: High.
- **BR-013**: Saved runtime-input preset entries are workflow-scoped, bounded per package/workflow scope, and marked stale when manifest, compiled-plan, or schema fingerprints drift. Evidence: `backend/app/services/workflow_package_runtime_input_registry.py`, frontend launch/runtime-input tests. Confidence: High.
- **BR-014**: Schedule detail reads intentionally omit editable input-template fields, while run-now remains idempotent and allowed for paused schedules. Evidence: `backend/app/schemas/schedule.py`, `backend/tests/test_workflow_package_runtime_api.py`. Confidence: High.
- **BR-015**: Deleting a model connection removes the live saved row but does not cascade current packages or historical run snapshots that still reference its key. Evidence: `backend/app/services/model_connection_service.py`, `backend/tests/test_runtime_repositories.py`. Confidence: High.
- **BR-016**: Reports are listed newest-first and have no automatic expiration or cleanup contract; removal happens only through explicit delete paths, including report deletion by slug and run deletion for run-owned agent-memory report rows. Evidence: `backend/app/repositories/report.py`, `backend/app/api/reports.py`, `backend/app/services/run_service.py`, `backend/tests/test_api.py::test_report_external_non_memory_update_and_delete_remains_allowed`, `backend/tests/test_runtime_repositories.py::test_delete_run_route_returns_204_then_404`. Confidence: High.
- **BR-017**: Workflow Package import/export is a current-contract artifact flow; removed version/status selection and long-term backward-compatibility guarantees are not part of the live contract. Evidence: `backend/tests/test_workflow_package_api.py`, `backend/app/services/workflow_package_export.py`. Confidence: High.
- **BR-018**: Structured runtime-input authoring is limited to the current supported object-schema subset; unsupported schemas remain on raw JSON fallback rather than implying broader structured-editor support. Evidence: `frontend/src/lib/platform-authoring/schema/launch-input-state.test.ts`, `docs/spec.md`. Confidence: High.
- **BR-019**: The dashboard contract is limited to the stable landing header and retry behavior evidenced in code/tests; richer summary cards or metrics are not part of the confirmed contract. Evidence: `frontend/src/pages/dashboard.tsx`, `frontend/src/pages/dashboard.test.tsx`. Confidence: High.
- **BR-020**: Hard deletion of runs is a live public API feature; deleting a run removes the targeted run, removes its run-owned agent-memory report rows, and nulls descendant lineage references rather than cascading descendant runs. Evidence: `backend/app/api/runs.py`, `backend/tests/test_runtime_repositories.py`. Confidence: High.

## 10. Permissions, Auth, Security, And Privacy Requirements

- **Confirmed**: Extension-owned finance routes and tools are blocked or hidden when `signaldeck.finance` is disabled. Evidence: `backend/app/extensions/signaldeck_finance/api_routers.py`, `backend/app/services/extension_service.py`, `frontend/src/extensions/runtime-helpers.ts`.
- **Confirmed**: Package secret bindings are encrypted at rest and omitted from read/export surfaces. Evidence: `backend/app/models/workflow_package.py`, `backend/app/schemas/workflow_package.py`, `backend/tests/test_workflow_package_run_contracts.py`, `backend/tests/test_workflow_package_export.py`.
- **Confirmed**: Inline private MCP descriptor values remain part of manifest hydration/export behavior even though package secret bindings do not. Evidence: `backend/tests/test_workflow_package_runtime_api.py`, `docs/spec.md`.
- **Confirmed**: Model-connection secrets are encrypted at rest and never returned in read payloads. Evidence: `backend/app/models/model_connection.py`, `backend/app/schemas/model_connection.py`.
- **Confirmed**: HTTP operation execution blocks insecure or private-network access by default, caps body sizes, and blocks redirects unless configured otherwise. Evidence: `backend/app/core/config.py`, `backend/app/services/http_operation_execution_service.py`, `backend/tests/test_http_operation_execution_service.py`.
- **Confirmed**: Memory namespace access is grant- and scope-aware, not open global access. Evidence: `backend/app/schemas/memory.py`, `backend/tests/test_memory_service.py`.
- **Confirmed**: The live product contract is trusted single-user; authentication, authorization, tenancy, and separate human permission roles are out of scope rather than deferred live surfaces. Evidence: `docs/prd.md`, absence of auth middleware or role DTOs in `backend/app/main.py` and the live route/API surface.
- **Confirmed**: `Workflow package author` is a capability mode of the trusted operator, not a separately enforced role model. Evidence: actor surface review across `frontend/src/routes.ts`, `frontend/src/pages/workflow-packages/*`, and `backend/app/api/workflow_packages.py`.
- **Confirmed**: The current contract does not include any broader privacy, retention, or regulatory policy beyond the technical controls directly evidenced in code and tests. Evidence: secret-safe reads, browser-safe errors, explicit persistence/delete semantics, and absence of policy-layer code or docs in the live implementation.

## 11. Integration Requirements

| Integration | Purpose | Trigger | Data exchanged | Failure behavior | Evidence |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | Authoritative persistence for finance and platform tables | app startup and request handling | ORM rows, JSONB artifacts, schedule/run state | readiness fails closed; startup upgrade path repairs schema | `backend/app/db/session.py`, `backend/app/db/upgrades.py` |
| OpenAI-compatible model endpoints | Run package agents and model connection tests/probes | launch, preflight, run execution, test/probe actions | model prompts, structured outputs, capability status | backend-owned validation and retry policy; secret-safe messages | `backend/app/services/model_gateway*.py`, `backend/app/api/model_connections.py` |
| Quote provider (`yahoo` or `deterministic`) | Quotes, history, symbol names | finance market-data calls and lookups | symbols, quotes, history | degraded warnings and cache fallback | `backend/app/core/config.py`, `backend/app/extensions/signaldeck_finance/services/market_data_service.py` |
| Digital Oracle providers | Prediction markets, SEC filings, and market sentiment runtime tools | granted runtime tool calls | normalized DTOs plus warnings | warnings/degraded results; extension-owned visibility | `backend/app/extensions/signaldeck_digital_oracle/*`, `backend/tests/test_runtime_tools.py` |
| Package-private MCP runtime | Package-local external tool dispatch | package runtime when MCP descriptors are granted | descriptor config, tool IO, redacted output | strict descriptor/hash/security validation | `backend/app/agents/mcp/runtime.py`, `backend/tests/test_mcp_runtime.py` |
| Logfire | Optional traces/spans for run observability | app startup and run execution | trace/span ids and metadata | execution remains functional without token | `backend/app/core/telemetry.py`, `docs/spec.md` |
| Docker / GHCR / local compose | Development and release packaging | local startup or CI image publishing | containers and env config | production runtime fails closed on missing required config | `README.md`, `.github/workflows/docker-images.yml` |

## 12. Non-Functional Requirements

- **Performance (Confirmed)**: Scheduler concurrency and polling are configurable through runtime settings such as `RUN_SCHEDULER_MAX_ACTIVE_RUNS`, `RUN_SCHEDULER_MAX_ACTIVE_PER_PACKAGE`, and poll/heartbeat/lease TTL settings. Evidence: `backend/app/core/config.py`, `backend/app/workers/run_scheduler.py`.
- **Reliability (Confirmed)**: Local persistence remains usable when quote/model/optional external providers degrade; scheduled previews validate before persistence; queued runs are executed by a lease-aware worker. Evidence: `backend/tests/test_api.py`, `backend/tests/test_workflow_package_preflight.py`, `backend/app/workers/run_scheduler.py`.
- **Observability (Confirmed)**: Logfire traces/spans are optional and persisted as metadata when available; scheduler logs materialization and stale-lease recovery events. Evidence: `backend/app/main.py`, `backend/app/workers/run_scheduler.py`, `docs/spec.md`.
- **Scalability (Confirmed)**: The run queue serializes by package lane and worker slot rather than executing all runs inline in request handlers. Evidence: `backend/tests/test_runtime_repositories.py`, `backend/app/workers/run_scheduler.py`.
- **Operational SLA (Confirmed out-of-scope)**: The current contract does not guarantee queue latency, throughput, or execution-time SLAs for queued runs; only worker mechanics and configurable limits are evidenced. Evidence: `backend/app/workers/run_scheduler.py`, queue-related backend tests, absence of SLA-oriented contract code.
- **Accessibility (Confirmed decision)**: The frontend follows semantic/accessibility-oriented patterns such as labeled search/controls, ARIA usage, and accessibility-conscious shared component guidance, but no formal WCAG/axe compliance target is part of the current contract. Evidence: frontend route/component tests, `frontend/src/components/shared/docs/ui-library-reference.md`, absence of formal accessibility-target tooling.
- **Internationalization / localization (Confirmed decision)**: The current contract is English-only; no translation layer, locale-content system, or i18n framework is implemented. Evidence: absence of i18n libraries/framework usage in frontend/backend code and tests.
- **Compatibility (Confirmed)**: Backend requires Python 3.13+, frontend targets Node 24 and pnpm 10, and the backend requires PostgreSQL. Evidence: `README.md`, `backend/app/db/session.py`.
- **Maintainability (Confirmed)**: The repo maintains canonical owner docs, explicit extension boundaries, CI quality gates, and route metadata/test coverage. Evidence: `docs/*.md`, `.github/workflows/ci.yml`, `frontend/src/routes.test.tsx`.
- **Compliance / privacy (Confirmed decision)**: Secret-safe reads, encryption, browser-safe error shaping, and explicit persistence/delete semantics are part of the live contract; no broader regulatory/privacy program is part of the current contract. Evidence: `backend/app/main.py`, `backend/app/models/model_connection.py`, `backend/app/models/workflow_package.py`, persistence and delete-path code/tests.

## 13. Error Handling And Failure Modes

- Request validation failures use the shared validation envelope from `backend/app/main.py`.
- Domain/business-rule failures use shared `ApiError` envelopes with browser-safe `details`.
- Finance-extension-disabled requests are blocked by extension gates.
- Market-data provider failures degrade to warnings and/or cached results when possible.
- Template compilation can fail on missing inputs or placeholder cycles.
- Report creation can fail on slug conflicts or invalid public provenance.
- Workflow package validation can fail on malformed YAML, forbidden keys, unsupported features, unresolved refs, or preflight blockers.
- HTTP operation nodes fail closed on unsupported methods, insecure/private-network URLs, redirect violations, oversize bodies, unsupported content types, invalid JSON, or output-schema mismatches.
- Scheduled Task previews surface placeholder and schema validation errors before run creation.
- Run list filters reject deprecated target filters.
- Memory writes may surface retryable revision conflicts; memory access may fail for missing context, invalid ids, or namespace grant denial.

## 14. Traceability Matrix

The full requirement-to-evidence matrix is maintained in the companion file:

- `docs/requirements/traceability-matrix.md`

That file maps each `FR-*` identifier to routes, schemas, models, services, docs, and tests. This section is intentionally brief to avoid duplicating the matrix.

## 15. Gaps, Contradictions, And Open Questions

The full open-question and weak-evidence register is maintained in the companion file:

- `docs/requirements/open-questions.md`

After this resolution pass, no remaining contract-level open questions were left in the current product baseline. Former open questions were either promoted into confirmed requirements/business rules or converted into explicit out-of-scope statements.

### Unsupported Or Out-Of-Scope Requirement Themes

The following requirement themes are intentionally excluded from the confirmed contract:

- Formal user-role separation, multi-user auth, or tenant isolation.
- Any Digital Oracle route, page, or nav surface.
- Any live global authoring surface outside Workflow Packages.
- Any public global memory CRUD or unscoped search contract.
- Long-term backward-compatibility guarantees for Workflow Package import/export.
- Queue latency or throughput SLAs for run execution.
- Formal WCAG/accessibility certification targets.
- Localization or multilingual UI support.
- Any production compliance/privacy regime beyond the technical controls directly evidenced in code and tests.
- Dashboard summary cards, metrics, or charts beyond the narrow landing contract currently implemented.

## 16. Final Verification

This reverse-engineered document was finalized by re-checking the following evidence layers against one another:

- Top-level route registry, route metadata, and extension gates.
- Backend route modules, schemas, models, scheduler worker, and key service boundaries.
- Backend regression tests for finance CRUD, workflow packages, schedules, runs, tools, memory, and removed surfaces.
- Frontend unit and Playwright tests for navigation, workflow packages, scheduled tasks, runs, extensions, memory, and reports.
- Existing canonical docs (`README.md`, `docs/prd.md`, `docs/requirements.md`, `docs/spec.md`, `docs/data-model.md`, `docs/test-plan.md`) as corroborating evidence only where they matched live code and tests.
- An Oracle audit that downgraded or clarified overclaims around memory creation, secret export wording, schedule hidden rules, model-connection delete semantics, runtime-input registry behavior, and agent-report wording.

The final result is intended as a baseline requirements document that is explicit about uncertainty rather than silently inferring unsupported product intent.
