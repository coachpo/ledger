# Current Architecture Diagrams

These diagrams describe the current implemented architecture only. They do not propose target architecture or remediation.

## Diagram Legend

- `implemented`: live route, service, model, schema, worker, or frontend wiring evidence exists.
- `tested`: implementation evidence plus named automated test evidence exists.
- `documented only`: repo documentation evidence exists, but this pass did not confirm live implementation.
- `not found`: baseline/checklist expectation was searched for but not found in inspected live code.

## Backend Router Composition

```mermaid
flowchart TD
  create_app["create_app()\nimplemented"] --> platform["platform_router prefix /api\ntested"]
  create_app --> v1["api_router prefix /api/v1\ntested"]
  platform --> ext_api["/api/extensions\nimplemented"]
  platform --> memory_api["/api/memory\nimplemented"]
  platform --> model_api["/api/model-connections\nimplemented"]
  platform --> tools_api["/api/tools\nimplemented"]
  platform --> packages_api["/api/workflow-packages\ntested"]
  platform --> schedules_api["/api/schedules\ntested"]
  platform --> runs_api["/api/runs\ntested"]
  v1 --> bundled["bundled extension router contributions\nimplemented"]
  bundled --> finance_routes["Finance /api/v1 portfolios/templates/reports/etc.\ntested"]
```
Evidence notes: `backend/app/main.py:41`, `backend/app/main.py:90`, `backend/app/api/platform_router.py:12`, `backend/app/api/router.py:5`, `backend/app/extensions/signaldeck_finance/api_routers.py:34`, `backend/tests/test_legacy_backend_cutover.py:62`.

## Workflow Package Launch And Run Execution

```mermaid
sequenceDiagram
  participant Browser as Browser Workflow Package UI
  participant API as /api/workflow-packages
  participant WPS as WorkflowPackageService
  participant RS as RunService
  participant DB as PostgreSQL runs tables
  participant Worker as RunSchedulerWorker
  participant Queue as RunQueueService

  Browser->>API: POST /{package_id}/launches
  API->>WPS: create_launch(package_id, payload)
  WPS->>RS: create_workflow_package_launch()
  RS->>DB: insert queued Run + planned rows
  Note over RS,DB: implemented queue-only launch
  Worker->>Queue: claim_next_run()
  Queue->>DB: mark running + lease metadata
  Worker->>RS: execute_claimed_run(run_id)
  RS->>DB: persist steps, invocations, trace id, final status
  Note over Worker,RS: tested by runtime API and run contract tests
```

Evidence notes: `backend/app/api/workflow_packages.py:313`, `backend/app/services/workflow_package_service.py:283`, `backend/app/services/run_service.py:397`, `backend/app/services/run_queue_service.py:80`, `backend/app/workers/run_scheduler.py:183`, `backend/tests/test_workflow_package_runtime_api.py:956`.

## Scheduled Task Materialization

```mermaid
sequenceDiagram
  participant API as /api/schedules
  participant ScheduleService as WorkflowPackageScheduleService
  participant ScheduleDB as workflow_package_schedules / fires
  participant Materializer as WorkflowPackageScheduleMaterializer
  participant RunService as RunService
  participant RunsDB as runs
  participant Worker as RunSchedulerWorker

  API->>ScheduleService: create/update/preview/run-now
  ScheduleService->>ScheduleDB: persist structured recurrence and fires
  Worker->>Materializer: materialize_due()
  Materializer->>ScheduleService: list_due_schedules(lock_rows=true)
  Materializer->>ScheduleDB: insert or reuse fire row
  Materializer->>ScheduleService: queue_schedule_fire_run()
  ScheduleService->>RunService: create_scheduled_workflow_package_run()
  RunService->>RunsDB: insert ordinary queued Run with schedule provenance
  Worker->>RunsDB: claim and execute through queue flow
```

Evidence notes: `backend/app/api/schedules.py:23`, `backend/app/schemas/schedule.py:49`, `backend/app/services/workflow_package_schedule_materializer.py:82`, `backend/app/services/workflow_package_schedule_service.py:454`, `backend/app/workers/run_scheduler.py:107`, `backend/tests/test_runtime_repositories.py:1748`.

## Extension Gating And Ownership

```mermaid
flowchart LR
  Registry["BundledExtensionRegistry\nimplemented"] --> Finance["signaldeck.finance\ntested"]
  Registry --> DigitalOracle["signaldeck.digital_oracle\ntested"]
  ExtensionState["extension_states table\nimplemented"] --> ExtensionService["ExtensionService\ntested"]
  Registry --> ExtensionService
  ExtensionService --> PublicState["/api/extensions: key, label, enabled\ntested"]
  ExtensionService --> ToolCatalog["ToolCatalog enabled tool view\ntested"]
  ExtensionService --> RuntimeRegistry["RuntimeToolRegistry enabled tool view\ntested"]
  Finance --> FinanceRoutes["Finance /api/v1 route registrations\ntested"]
  Finance --> FinanceTools["Finance server/runtime tools\ntested"]
  DigitalOracle --> DOTools["Digital Oracle server/runtime tools only\ntested"]
  DigitalOracle -. no routes/nav .-> NoRoute["route/nav surface not found"]
```

Evidence notes: `backend/app/extensions/registry.py:279`, `backend/app/services/extension_service.py:94`, `backend/app/services/extension_service.py:97`, `backend/app/services/extension_service.py:165`, `backend/app/extensions/signaldeck_finance/api_routers.py:34`, `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts:21`, `backend/tests/test_extensions_api.py:50`, `backend/tests/test_tool_catalog_api.py:399`.

## Tools, MCP, And Memory Boundary

```mermaid
flowchart TD
  ToolsAPI["/api/tools\nimplemented"] --> ToolCatalog["ToolCatalog\ntested"]
  ToolCatalog --> CoreTools["Core memory tools\ntested"]
  ToolCatalog --> ExtensionTools["Extension server-declared tools\ntested"]
  RuntimeRegistry["RuntimeToolRegistry\ntested"] --> GrantCheck["granted tool keys\nimplemented"]
  RuntimeRegistry --> EnabledCheck["enabled extension state\nimplemented"]
  GrantCheck --> NativeDispatch["native runtime dispatch\ntested"]
  EnabledCheck --> NativeDispatch
  McpRuntime["MCP runtime dispatcher\ntested"] --> McpSecurity["URL/stdio validation + redaction\ntested"]
  MemoryAPI["/api/memory POST access-context routes\nimplemented"] --> MemoryService["MemoryService\ntested"]
  CoreTools --> MemoryService
  MemoryService --> MemoryTables["agent_memory_* tables\ntested"]
```

Evidence notes: `backend/app/api/tools.py:14`, `backend/app/agents/tool_catalog/server_declared.py:7`, `backend/app/agents/runtime_tools/registry.py:84`, `backend/app/agents/mcp/runtime.py:111`, `backend/app/agents/mcp/security.py:44`, `backend/app/api/memory.py:22`, `backend/tests/test_runtime_tools.py:3377`, `backend/tests/test_memory_service.py:646`.

## Frontend Route And Navigation Assembly

```mermaid
flowchart TD
  Routes["routes.ts\nimplemented"] --> FinanceRoutes["assembleFinanceWorkspaceRoutes()\nimplemented"]
  Routes --> PlatformRoutes["platform routes\nimplemented"]
  FinanceScaffold["Finance scaffold\nimplemented"] --> FinanceRoutes
  DigitalOracleScaffold["Digital Oracle tool-only scaffold\ntested"] --> ToolFilter["filterToolsForExtensionState()\ntested"]
  ExtensionAPI["/api/extensions state\ntested"] --> RuntimeHelpers["runtime-helpers.ts\ntested"]
  RuntimeHelpers --> NavGroups["assembleNavGroups()\ntested"]
  RuntimeHelpers --> ToolFilter
  Metadata["routes.metadata.ts\ntested"] --> NavGroups
  Metadata --> Layout["Layout shell\nimplemented"]
  Routes --> RouterTests["routes.test.tsx\ntested"]
```

Evidence notes: `frontend/src/routes.ts:29`, `frontend/src/routes.ts:30`, `frontend/src/extensions/runtime-helpers.ts:110`, `frontend/src/extensions/runtime-helpers.ts:173`, `frontend/src/extensions/signaldeck-digital-oracle/scaffold.ts:21`, `frontend/src/routes.metadata.ts:65`, `frontend/src/routes.test.tsx:177`.

## Persistence And Schema Authority

```mermaid
flowchart TD
  InitDB["init_db()\nimplemented"] --> Metadata["Base.metadata.create_all\nimplemented"]
  InitDB --> Upgrades["upgrade_legacy_schema\ntested"]
  Models["SQLAlchemy models\nimplemented"] --> WorkflowPackages["workflow_packages + secret bindings + runtime inputs\nimplemented"]
  Models --> Runs["runs + run snapshots + leases + schedule provenance\ntested"]
  Models --> Schedules["workflow_package_schedules + fires\ntested"]
  Models --> ModelConnections["model_connections encrypted secret_payload\nimplemented"]
  Models --> Extensions["extension_states\nimplemented"]
  Upgrades --> RuntimeDBTests["runtime DB upgrade tests\ntested"]
```

Evidence notes: `backend/app/db/session.py:16`, `backend/app/db/session.py:23`, `backend/app/db/session.py:31`, `backend/app/models/workflow_package.py:16`, `backend/app/models/run.py:15`, `backend/app/models/workflow_package_schedule.py:15`, `backend/app/models/model_connection.py:159`, `backend/tests/test_runtime_db_upgrades.py:2288`.

## Removed Or Not Found Surfaces

```mermaid
flowchart TD
  PlatformRouter["platform_router /api\nimplemented"] --> LiveOnly["extensions, memory, model-connections, tools, workflow-packages, schedules, runs\ntested"]
  PlatformRouter -. no mounted router .-> RemovedBackend["global agents/workflows/capabilities/MCP/output schemas/skills\nnot found"]
  BrowserRouter["routes.ts\nimplemented"] --> LiveBrowser["Finance routes + platform routes\ntested"]
  BrowserRouter -. wildcard .-> RemovedBrowser["legacy authoring, Studio, Tryout, orchestration, backtests, /api/* browser routes\nnot found"]
  ScheduleSchema["schedule.py structured recurrence\nimplemented"] -. live cron search .-> RawCron["raw cron contract\nnot found"]
```

Evidence notes: `backend/app/api/platform_router.py:4`, `backend/app/api/platform_router.py:12`, `backend/tests/test_legacy_backend_cutover.py:46`, `frontend/src/routes.ts:51`, `frontend/src/routes.test.tsx:459`, `frontend/src/routes.test.tsx:510`, `backend/app/schemas/schedule.py:49`, live-code search for `cron|crontab|Cron`.

## Status-Labeled Diagram Notes

- `tested`: Router, launch queue, schedule materialization, extension gating, frontend routing, and CI-backed coverage are represented with automated-test anchors.
- `implemented`: Low-level persistence and schema authority diagrams use model/service/schema evidence even when the diagram node itself is not a single test assertion.
- `documented only`: This diagrams file itself is part of the documentation-only audit workspace.
- `not found`: Raw cron, Digital Oracle frontend route/nav, and removed global authoring route surfaces were not found in the inspected live router composition.
