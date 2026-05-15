# Ledger Agent Platform Reference

> Status: Live package-first platform reference for branch `main` at `33c2584`. This is the canonical platform reference.

## Scope

Ledger ships a package-first agent platform beside the preserved portfolio, template, and report product areas. Users author Workflow Packages, bind package agents to global Model Connections, reference read-only global Tools, launch package runs, and inspect persisted Runs from the browser.

This document describes shipped behavior only. Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract pages, and retired legacy global authoring routes are not live surfaces.

## Live Surfaces

| Area | Backend | Frontend |
|---|---|---|
| Workflow Packages | `/api/workflow-packages*` | `/workflow-packages*` |
| Package Secret Bindings | `/api/workflow-packages/{packageId}/secret-bindings*` | Secret Bindings tab inside `/workflow-packages/{packageId}` |
| Model Connections | `/api/model-connections*` | `/model-connections*` |
| Extensions | `/api/extensions*` | extension state consumers |
| Tools | `/api/tools` | surfaced inside package capability-profile editors |
| Runs | `/api/runs*` | `/runs*` |

Preserved finance product routes remain under `/api/v1` and `/portfolios*`, `/templates*`, and `/reports*`. They are bundled in `ledger.finance`, which is enabled by default and supports enable/disable state only. Generic platform capabilities remain core: Workflow Packages, Model Connections, Runs, HTTP operation nodes, package secret bindings, manifest parsing, and the `/api/tools` discovery host.

## Workflow Packages

Workflow Packages are the only live platform authoring root. Manifests use `ledger.workflowPackage/v1` YAML and store package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes inside immutable package versions.

Package-local refs use local keys. Model bindings use global Model Connection keys. Tool grants use global server-declared tool keys inside package-local capability profiles. Workflow graph nodes currently ship as `kind: step`, `kind: sequence`, `kind: fanout`, `kind: loop`, and `kind: http`.

`kind: step` continues to mean local package-agent invocation through `AgentExecutionService`. `kind: http` is the shipped non-agent operation node; it compiles into `ExecutionPlanOperation` and `PackageRuntimeOperationSpec`, not into fake agents. Mixed execution steps may carry both `agents` and `operations`; final outputs still resolve from step/slot selectors such as `${{ nodes.notify_slack.outputs.webhook_result }}`.

Package import/export is manifest based. Exports keep private MCP `env`, `headers`, and `query` values inline in the package text. This is an intentional breaking change, and the old binding-based private MCP contract no longer applies. Exports still omit database ids, run history, package secret binding rows, and raw package secret binding values.

## HTTP Operation Nodes

The public manifest contract for non-agent operations is `kind: http`:

```yaml
flow:
  kind: http
  id: notify_slack
  slot: webhook_result
  method: POST
  url: ${{ inputs.webhookUrl }}
  headers:
    Authorization: ${{ secrets.slack_webhook_token }}
  query:
    ticker: ${{ inputs.ticker }}
  body:
    ticker: ${{ inputs.ticker }}
  response:
    outputSchema: webhook_response
  timeoutSeconds: 10
  optional: false
```

`id` and `slot` are lowercase package-local identifiers. `method` is normalized to uppercase and preflight allows `GET` and `POST`. `url`, `headers`, `query`, and `body` may use literal JSON-compatible values, input refs, prior-node output refs, and `${{ secrets.key }}` refs. Secret refs are valid only in those HTTP request fields and compile to `{from:"secret", key:"..."}` for runtime resolution.

The HTTP runtime is intentionally narrow. `HttpOperationExecutionService` resolves request inputs, prior slot outputs, and package secret binding values immediately before dispatch. It enforces HTTPS by default, blocks private/loopback/link-local/reserved targets by default, caps timeout/request/response sizes, disables redirects by default, and validates JSON/text responses against `response.outputSchema`. The test-only dev override path is covered by `dev_override` tests and does not weaken production defaults.

## Package Secret Bindings

Package secret bindings are package-local encrypted values used by HTTP operation nodes. They are not Workflow Package manifest fields and are never included in exports, run details, logs, compiled graph refs, agent inputs, workflow outputs, or diagnostics.

The API shape is:

- `GET /api/workflow-packages/{packageId}/secret-bindings` -> `{items:[{packageId,key,hasValue,createdAt,updatedAt}]}`
- `PUT /api/workflow-packages/{packageId}/secret-bindings/{key}` with `{value}` -> `{packageId,key,hasValue,createdAt,updatedAt}`
- `DELETE /api/workflow-packages/{packageId}/secret-bindings/{key}` -> `204`

The frontend exposes this through the package editor Secret Bindings tab. Stored values are never echoed; the UI shows known keys and stored/redacted state, clears typed values after save, and sends new values only through the update request.

## Model Connections

Model Connections are global live bindings for provider endpoint, model id, API style, reasoning effort, timeout defaults, encrypted API keys, status, and last connection-test metadata.

Read payloads and errors must mask or omit raw secrets. Blank API-key edits preserve the stored key; non-empty edits rotate it. Packages resolve Model Connections by key during validation, preflight, launch, and runtime.

## Tools

Tools are read-only server-declared metadata from `/api/tools`. Packages reference tool keys through local capability profiles; the platform does not expose global capability CRUD as a live route. The host is core, while the current finance/product/provider tool entries are `ledger.finance` contributions.

Current native tools cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, report lookup, and report memory writes. They remain visible to smoke and demo Workflow Packages while `ledger.finance` is enabled by default. Runtime tool keys and OpenAI function names stay stable. Examples include `ledger.market_data.ohlcv_lookup`, `ledger.indicators.lookup`, `ledger.news.lookup`, `ledger.social_sentiment.lookup`, `ledger.reports.lookup`, `ledger.reports.write`, and OpenAI function names such as `ledger_social_sentiment_lookup` and `ledger_reports_lookup`.

`ledger.news.lookup` remains the company/query/macro news contract. `ledger.social_sentiment.lookup` is separate and additive: it accepts `symbol`, optional `sources` (`reddit`, `stocktwits`), optional `startDate`, optional `endDate`, and optional `itemLimit` capped at `50`; output contains `sourceBlocks`, aggregate `metrics`, and structured `warnings`. Provider outage, timeout, rate-limit, empty-source, partial-result, and truncation paths return deterministic warnings rather than raw provider errors.

The canonical TradingAgents-style advisory package grants native data/news/social/report tools through package-local capability profiles, uses explicit analyst `sequence` topology, and remains advisory-only. It may propose a portfolio decision but does not execute trades, draft brokerage operations, or add LangGraph-specific checkpoint/runtime semantics.

## Runs

Package launch reads metadata from `GET /api/workflow-packages/{packageId}/launch`, then creates a run with `POST /api/workflow-packages/{packageId}/launches` using `{version, workflowKey, parameters}`.

Runs persist status, inputs, final output, token/timing totals, optional Logfire trace ids, per-agent invocation span ids, per-operation invocation span ids, rerun metadata, step replay metadata, and package provenance. Detail payloads include steps, agent invocations, and operation invocations for review without requiring a separate tracing product or Logfire token.

Run detail keeps operation invocation rows separate from agent rows. Each step has `invocations` for agents and `operationInvocations` for `kind: http` operations. Operation invocation detail includes `operationKey`, `operationKind`, `method`, `timeoutSeconds`, redacted `requestMetadata`, bounded `responseMetadata`, `output`, `outputOrigin`, status/error fields, replay source fields, and timestamps. HTTP-only steps have no agent invocations; mixed steps can show both families.

Run memory artifacts are memory-domain payloads. They expose `memoryId`, `summary`, `status`, `createdAt`, provenance, graph metadata when available, and optional `auditLinks.report` for report open/download actions while reports remain the backing store. `MemoryFollowUpService.run_due(now)` runs synchronously at workflow-package run start and appends due report-backed reflections idempotently before normal step execution.

## UI Contract

`frontend/src/routes.ts` is the route source of truth. `frontend/src/components/layout.tsx` owns sidebar entries and breadcrumbs for Workflow Packages, Model Connections, and Runs.

List pages provide create/import actions, status/version badges, and archive/delete actions where supported. Editors use hooks and API modules rather than direct fetch calls from view code. Validation appears as inline alerts, field messages, toasts, and backend error-envelope messages.

Workflow Package and Template editor routes use the full-height layout region inside the normal shell. Workflow Package editing remains YAML-first for workflow graph changes; `kind: http` authoring lives in the manifest YAML, package secret binding editing lives in the Secret Bindings tab, and run detail renders operation invocation cards separately from agent invocation cards.

## Backend Shape

```text
backend/app/api/platform_router.py
backend/app/api/{workflow_packages,model_connections,tools,runs}.py
backend/app/services/{workflow_package_service,workflow_package_preflight,workflow_package_export,run_service,model_connection_service,http_operation_execution_service,memory_follow_up_service,social_sentiment_service}.py
backend/app/core/{config,telemetry}.py
backend/app/services/workflow_package_manifest_{parser,compiler,decompiler}.py
backend/app/schemas/{workflow_package,workflow_package_manifest,model_connection,run}.py
backend/app/models/{workflow_package,model_connection,run,run_step,run_agent_invocation,run_operation_invocation}.py
backend/app/repositories/{workflow_package_secret_binding,run_operation_invocation}.py
```

## Frontend Shape

```text
frontend/src/routes.ts
frontend/src/components/layout.tsx
frontend/src/pages/{workflow-packages,model-connections,runs}/
frontend/src/hooks/{use-workflow-packages,use-model-connections,use-runs}.ts
frontend/src/lib/api/{workflow-packages,model-connections,tools,runs}.ts
frontend/src/lib/types/{workflow-package,model-connection,tool,run}.ts
frontend/src/lib/platform-authoring/**
```

## Retired Surfaces

The retired legacy global authoring routes `/api/agents`, `/api/capabilities`, `/api/mcp-servers`, `/api/output-schemas`, `/api/workflows`, `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, and `/workflows*` are absent from the mounted app and the live router. They are not compatibility aliases or redirects.

Legacy/unmounted backend modules may still exist for cutover regression context, but current docs must not present them as live routes. Current guardrails live in `backend/tests/test_legacy_backend_cutover.py`, `backend/tests/test_workflow_package_openapi.py`, `frontend/src/routes.test.tsx`, and `frontend/src/platform-clean-break.test.ts`.

## Validation

Each milestone has a deterministic targeted command, and the combined command is the contract gate for this upgrade. Backend tests use in-process fakes, deterministic smoke model connections, local mock transports, and bounded provider fixtures rather than live third-party networks.

```bash
# Milestone 1: native data/news/social runtime tools and provider normalization
(cd backend && uv run pytest tests/test_runtime_tools.py tests/test_runtime_tools_social_sentiment.py tests/test_market_data_service.py tests/test_social_sentiment_service.py -k "social_sentiment or news_lookup_contract or news_adapter or social_adapter or timeout or rate_limit or empty_result or partial_result")

# Milestone 2: report-backed memory follow-up automation
(cd backend && uv run pytest tests/test_memory_service.py tests/test_memory_follow_up_service.py tests/test_report_backed_memory_store.py -k "matured_follow_up or append_reflection or idempotent or duplicate_resolution or run_start_follow_up")

# Milestone 3: canonical advisory package fixture behavior
(cd backend && uv run pytest tests/test_workflow_package_preflight.py tests/test_workflow_package_smoke_fixture.py tests/test_workflow_package_run_contracts.py -k "tradingagents_advisory_research or advisory_only_output or portfolio_decision")

# Milestone 4: HTTP node security, mixed execution, and run-detail rendering
(cd backend && uv run pytest tests/test_workflow_package_manifest_http_node.py tests/test_workflow_manifest_compiler.py tests/test_workflow_package_execution_plan_http.py tests/test_workflow_package_run_contracts.py tests/test_run_operation_invocations.py tests/test_http_operation_execution_service.py tests/test_run_service_http_operations.py tests/test_runtime_db_upgrades.py)
```

```bash
# Combined targeted backend validation from the implementation plan
(cd backend && uv run pytest tests/test_runtime_tools.py tests/test_runtime_tools_social_sentiment.py tests/test_market_data_service.py tests/test_social_sentiment_service.py tests/test_memory_service.py tests/test_memory_follow_up_service.py tests/test_report_backed_memory_store.py tests/test_workflow_package_preflight.py tests/test_workflow_package_manifest_http_node.py tests/test_workflow_manifest_compiler.py tests/test_workflow_package_execution_plan_http.py tests/test_workflow_package_run_contracts.py tests/test_run_operation_invocations.py tests/test_http_operation_execution_service.py tests/test_run_service_http_operations.py tests/test_runtime_db_upgrades.py)

# Frontend HTTP authoring, secret binding, and run-detail operation rendering
(cd frontend && pnpm test:run src/pages/workflow-packages/http-node-validation.test.tsx src/pages/workflow-packages/secret-bindings.test.tsx src/pages/runs/detail-http-operations.test.tsx)
(cd frontend && pnpm typecheck)

# Public contract docs grep check
rg -n "kind: http|ledger.social_sentiment.lookup|operation invocation|secret binding" docs/api-design.md docs/ledger-agent-platform.md
```

Security override coverage stays focused and test-only:

```bash
(cd backend && uv run pytest tests/test_http_operation_execution_service.py -k "dev_override or localhost_blocking")
```
