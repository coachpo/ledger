# Target Architecture

This target architecture turns the current audit baseline and gap register into the desired module shape for this repository. It is design-only. It does not introduce new product scope, compatibility promises, or implementation changes.

Primary evidence:

- `00-contract-baseline.md:13-23` defines the live platform boundaries.
- `00-contract-baseline.md:38-60` defines the non-negotiable architecture and deletion rules.
- `02-current-architecture.md:18-23` summarizes aligned live routes, package execution, extension state, and CI gates.
- `02-current-architecture.md:25-106` records the implemented backend, frontend, runtime, extension, memory, tools, and persistence anchors.
- `03-gap-register.md:29-70` records the four target deltas this architecture must address.
- `03-gap-summary.md:27-39` records the areas already aligned and worth preserving.

## Target Principles

- Workflow Packages are the only executable authoring root.
- Launch, rerun, fork, schedule preview, and schedule fire flows validate and persist intent; they do not execute workflows inline.
- Runtime execution starts from a persisted queued run that has been claimed by a worker.
- The worker executes immutable run snapshots, not mutable package state.
- PostgreSQL is the source of truth and initial queue.
- Platform core and extension-owned behavior stay separate unless an ADR explicitly promotes behavior into core.
- Removed global authoring surfaces are deleted, not wrapped, aliased, or adapted.

## Target Module Layout

The backend target follows clean architecture dependency direction:

```text
backend/app/api/                 # FastAPI route adapters and dependency factories
backend/app/application/         # use cases, command/query handlers, transaction orchestration
backend/app/domain/              # package, run, schedule, memory, extension, and finance domain rules
backend/app/ports/               # repository, provider, queue, runtime-tool, and clock interfaces
backend/app/infrastructure/      # SQLAlchemy, provider SDKs, crypto, telemetry, MCP transport, DB repair
backend/app/runtime/             # worker entrypoints and run-execution orchestration
backend/app/extensions/          # statically resident extension registrars and extension-owned behavior
backend/app/schemas/             # external API DTOs and shared envelope conventions
```

The frontend target keeps route-level ownership explicit:

```text
frontend/src/routes.ts                 # platform route table plus extension route assembly
frontend/src/routes.metadata.ts        # route ownership, shell, nav, and visibility metadata
frontend/src/extensions/               # statically resident frontend extension scaffolds
frontend/src/pages/workflow-packages/  # package-first authoring/import/export/launch UI
frontend/src/pages/scheduled-tasks/    # package-first automation UI
frontend/src/pages/runs/               # queued run, rerun, fork, and invocation detail UI
frontend/src/pages/memory/             # scoped platform memory UI
frontend/src/lib/api/                  # typed API clients and error parsing
```

Existing `services` modules can move into `application`, `domain`, `ports`, and `infrastructure` as they are split. Existing extension modules stay extension-owned unless an ADR explicitly promotes a behavior into platform core.

## Backend Layers And Allowed Dependencies

API modules are route adapters. They own FastAPI routing, request dependency injection, response DTO selection, and translation from domain/application errors into the shared `{code, message, details[]}` envelope. They may depend on application use cases, schema DTOs, and API dependency factories. They must not own workflow execution, scheduler loops, SQLAlchemy query logic, provider SDK calls, or extension-private behavior.

Application modules own use cases: validate package input, create package artifacts, preflight launches, create queued runs, render schedule previews, materialize schedule fires, query run details, resolve memory access contexts, and coordinate extension state. They may depend on domain types and ports. They own transaction boundaries through unit-of-work ports or infrastructure implementations; repository adapters should not commit independently. Business rules should remain in domain modules.

Domain modules own platform invariants: package-first authoring, run snapshot immutability, queue status transitions, recurrence value rules, scoped memory grants, extension state visibility, and secret absence from public reads. Domain code must not import FastAPI, SQLAlchemy sessions, provider clients, frontend concepts, extension router modules, or ports.

Ports define the contracts application use cases need from infrastructure: package repositories, run repositories, queue leases, schedule clocks, model-provider calls, runtime tool dispatch, MCP transport, encryption, telemetry, and extension contribution lookup. Domain code must not import ports; infrastructure implements those ports using SQLAlchemy, official provider SDKs, encrypted JSONB, Logfire, and MCP clients.

## Frontend Routing And Extension Layout

`frontend/src/routes.ts` remains the single browser route table. Platform routes stay explicit for Extensions, Workflow Packages, Scheduled Tasks, Model Connections, Memory, and Runs. Finance Workspace routes are assembled from the Finance extension scaffold through `assembleFinanceWorkspaceRoutes()`. No live `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` browser routes are added. Digital Oracle contributes no page or navigation surface.

`frontend/src/routes.metadata.ts` remains the ownership and shell contract for routes. Pages consume shared shell components and route metadata; they should not duplicate sidebar grouping or extension visibility rules. Extension state from the backend remains the only runtime visibility source for extension routes, navigation, and tool-prefix discovery.

Package authoring UI must use package-local DTOs and helpers. It should not import global `AgentRead`, `WorkflowRead`, or other removed global authoring wire types from legacy frontend type modules. Removed browser routes remain explicit 404/not-found behavior, not hidden compatibility pages.

## Runtime And Worker Boundaries

Run creation and run execution are separate target boundaries. Workflow Package launch, rerun, fork, and schedule-fire use cases create queued `Run` rows with immutable execution snapshots and provenance. They return run metadata to the caller and stop there. Recurrence math, queue claims, lease recovery, and runtime dispatch policy stay outside request handlers.

`RunSchedulerWorker` owns the loop that recovers stale leases, materializes due schedules, claims queued runs, heartbeats active leases, invokes runtime execution, and releases leases. Runtime code must not import FastAPI routers or depend on request-scoped objects. It receives a claimed run identity, loads the persisted snapshot, executes it, records invocation evidence, and writes terminal results through the reviewed queue/run boundary.

## Persistence And Migration Approach

PostgreSQL remains the authoritative store for packages, schedules, runs, model connections, extension state, memory, runtime inputs, and package secrets. Startup repair remains code-owned in `backend/app/db/`, but the target narrows it to live tables and live invariants only.

Retired-surface cleanup is not a product compatibility promise. Under the no-users baseline, repair logic for old global authoring tables, legacy skill storage, Studio, Tryout, orchestration-v2, runtime-v2, and other removed draft surfaces should be deleted after route/table absence checks prove those surfaces are outside the live contract.

Future persistence changes should enter through typed model/repository/infrastructure changes plus tests. Alembic scaffolds, generated caches, docs, and build output remain non-authoritative.

## Tool Catalog And Runtime Dispatch

`/api/tools` remains a read-only metadata surface. It exposes server-declared tool keys, display names, and descriptions after extension-state filtering. It does not expose runtime dispatch details, provider credentials, package-private MCP configuration, or extension-private registrars.

Runtime tool dispatch remains separate from catalog metadata. Dispatch checks enabled extension state, package grants, and tool arguments before executing. Platform-core memory tools stay platform-owned. Finance tools stay Finance-owned. Digital Oracle tools stay Digital Oracle-owned with no route or nav surface.

## Memory Access Model

Memory remains platform core and explicit-scope only. API and runtime callers must provide or derive a package-contextual access context before reads or writes. The browser keeps a single `/memory` route with no child detail routes. Public global memory CRUD, unscoped search, namespace-grant authoring, report-backed memory storage, vector search, embeddings, and chunk-table requirements remain out of scope.

The target keeps `signaldeck.memory.write` and `signaldeck.memory.lookup` as platform-owned runtime tools. Model-visible, API-visible, and UI-visible projections stay separate so runtime grants do not accidentally become public browse access. Historical agent reports and `signaldeck.reports.lookup` stay Finance/report history, not canonical memory storage.

## Extension Model

Extensions are statically resident code contributions. The backend registry declares private registrars; persisted extension state controls whether their public contributions are exposed. Public `/api/extensions` state stays slim: `key`, `label`, and `enabled` only.

Extension-owned contributions can include API routers, tools, runtime providers, lifecycle hooks, dependency surfaces, and frontend routes/nav where the extension contract allows it. Platform core must not infer extension-private metadata from public state. New shared behavior belongs in platform core only after an ADR defines it as a shared contract.

## Finance Extension Model

`signaldeck.finance` remains a first-party, statically resident extension-owned bounded context. It owns preserved Finance Workspace `/api/v1` route families, finance frontend routes/navigation, finance providers, finance runtime tools, report lookup, and finance-owned lifecycle/runtime behavior. Finance route and tool visibility stays gated by `signaldeck.finance` extension state.

Finance behavior should not silently redefine platform-core contracts. If a portfolio, report, market-data, or trading-tool behavior becomes a shared platform capability, an ADR must promote it explicitly and update routes, registries, docs, and tests together.

## Workflow Package Export Boundary

Workflow Package export is a trust boundary. The target must decide whether MCP `env`, `headers`, and `query` entries are public package configuration or secret-bearing material. Until that decision is made, export code remains a rewrite target rather than a stable compatibility surface.

The export target remains intentionally current-contract only. It must omit database ids, run history, package secret raw values, model connection secrets, and any field classified as secret-bearing. It must not preserve older draft export shapes through adapters or long-term compatibility paths.

## Acceptance Criteria

- No import cycles across target backend layers.
- API modules delegate to application use cases or services and never execute Workflow Packages inline.
- Runtime and worker modules do not import FastAPI router modules.
- Domain modules do not import SQLAlchemy sessions, provider SDK clients, FastAPI, frontend modules, or ports.
- Removed legacy route tests pass as 404/not-found for backend and browser routes.
- No auth, tenant, user, account, role, or permission tables or middleware are added unless a future live-contract ADR explicitly justifies them.
- Launch, rerun, fork, schedule preview, and schedule-fire endpoints never execute workflows inline.
- Tool metadata, runtime dispatch, memory access, and extension state remain separate surfaces.
- Digital Oracle remains tool-only; Finance remains extension-owned.
- Documentation, tests, and route registries name removed surfaces only as non-goals or deletion targets.
