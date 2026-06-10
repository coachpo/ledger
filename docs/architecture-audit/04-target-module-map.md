# Target Module Map

This map classifies current files and module families against the target architecture in `04-target-architecture.md`. It is documentation-only and does not rename or edit implementation files.

Status values are intentionally limited to:

- `keep in place`: the current location and responsibility already match the target boundary.
- `move`: the code should keep its responsibility but live under a clearer target layer or bounded context.
- `split`: the file currently mixes responsibilities that belong to separate target layers.
- `delete`: the code belongs to removed or non-contract surfaces and should not be preserved through aliases, wrappers, or compatibility adapters.
- `rewrite`: the behavior needs a sharper contract or boundary before it should be carried forward.

Primary evidence:

- `00-contract-baseline.md:13-23` for live platform scope.
- `00-contract-baseline.md:52-60` for delete-not-preserve rules.
- `02-current-architecture.md:25-106` for implemented file anchors.
- `03-gap-register.md:29-70` for the target deltas.

## Backend API And Composition

| Current path | Target home | Status | Reason |
| --- | --- | --- | --- |
| `backend/app/main.py` | `backend/app/main.py` | keep in place | App factory, health/readiness, CORS, and shared error handlers are composition concerns already evidenced in `02-current-architecture.md:27`. |
| `backend/app/api/platform_router.py` | `backend/app/api/platform_router.py` | keep in place | Platform `/api/*` route composition is aligned and contains the current platform route set only. |
| `backend/app/api/router.py` | `backend/app/api/router.py` | keep in place | `/api/v1` assembly from bundled extension router contributions preserves the platform/extension split. |
| `backend/app/api/dependencies.py` | `backend/app/api/dependencies.py` plus `backend/app/application/*` factories | split | Request dependency wiring can stay in API, while use-case construction should move toward application factories. |
| `backend/app/api/workflow_packages.py` | `backend/app/api/workflow_packages.py` | keep in place | Route adapter should remain thin and delegate package use cases; no inline execution. |
| `backend/app/api/schedules.py` | `backend/app/api/schedules.py` | keep in place | Route adapter for package-first Scheduled Tasks remains a platform API surface. |
| `backend/app/api/runs.py` | `backend/app/api/runs.py` | keep in place | Route adapter for queued run reads, reruns, and forks remains a platform API surface. |
| `backend/app/api/tools.py` | `backend/app/api/tools.py` | keep in place | Read-only tool metadata endpoint is already slim. |
| `backend/app/api/memory.py` | `backend/app/api/memory.py` | keep in place | Scoped access-context memory API remains platform core. |

## Backend Application, Domain, Ports, And Infrastructure

| Current path | Target home | Status | Reason |
| --- | --- | --- | --- |
| `backend/app/services/workflow_package_service.py` | `backend/app/application/workflow_packages/*` plus package domain modules | split | Current service owns package application flow; parsing, artifact rules, preflight, and persistence should separate into application, domain, and infrastructure. |
| `backend/app/services/run_service.py` | `backend/app/application/runs/*`, `backend/app/domain/runs/*`, `backend/app/infrastructure/runs/*` | split | Run creation, runtime execution, persistence writes, lineage, and terminal status handling cross target layers. |
| `backend/app/services/run_queue_service.py` | `backend/app/application/runs/queue.py` plus `backend/app/ports/run_queue.py` and infrastructure implementation | split | Queue claim, heartbeat, release, and stale recovery need an explicit port and reviewed terminal-write boundary. |
| `backend/app/workers/run_scheduler.py` | `backend/app/runtime/run_scheduler.py` | move | Worker entrypoint should live under runtime so API and worker dependencies are visibly separate. |
| `backend/app/services/workflow_package_schedule_materializer.py` | `backend/app/application/schedules/materialize.py` | move | Due-fire materialization is an application use case over schedule/run repositories and clock ports. |
| `backend/app/services/workflow_package_schedule_inputs.py` | `backend/app/domain/schedules/input_templates.py` | move | Placeholder rendering rules are package-first schedule domain rules. |
| `backend/app/services/workflow_package_manifest_parser.py` | `backend/app/domain/workflow_packages/manifest_parser.py` | move | Manifest validation is package-domain behavior independent of FastAPI and SQLAlchemy. |
| `backend/app/services/workflow_package_export.py` | `backend/app/application/workflow_packages/export.py` | split | Export is a trust boundary with a settled rule: private MCP `env`, `headers`, and `query` are secret-bearing and omitted from exported/browser-visible package material. |
| `backend/app/models/workflow_package.py` | `backend/app/infrastructure/persistence/models/workflow_package.py` | move | SQLAlchemy models are infrastructure details for package persistence. |
| `backend/app/models/run.py` | `backend/app/infrastructure/persistence/models/run.py` | move | Run storage remains PostgreSQL-backed infrastructure. |
| `backend/app/models/workflow_package_schedule.py` | `backend/app/infrastructure/persistence/models/workflow_package_schedule.py` | move | Schedule and fire rows are persistence details behind schedule/run repositories. |
| `backend/app/repositories/*` live package/run/schedule/model-connection modules | `backend/app/infrastructure/persistence/repositories/*` behind `backend/app/ports/*` | split | Repository behavior should implement ports instead of being imported as broad application services. |
| `backend/app/schemas/common.py` | `backend/app/schemas/common.py` | keep in place | CamelCase, decimal string, UTC timestamp, and forbidden-extra conventions are API DTO concerns. |
| `backend/app/schemas/workflow_package.py` | `backend/app/schemas/workflow_package.py` plus domain package types | split | External DTOs stay in schemas; package invariants should move to domain types. |
| `backend/app/schemas/run.py` | `backend/app/schemas/run.py` plus domain run types | split | External run projections stay in schemas; status-transition rules should live in domain. |
| `backend/app/db/session.py` | `backend/app/infrastructure/persistence/session.py` | move | Session creation and DB initialization are infrastructure concerns. |
| `backend/app/db/upgrades.py` | live repair modules under infrastructure persistence | rewrite | Keep live repair only; remove retired-surface startup repair ballast. |

## Backend Removed Global Authoring Ballast

| Current path | Target home | Status | Reason |
| --- | --- | --- | --- |
| `backend/app/models/agent.py` | none | delete | Standalone global agents are removed authoring ballast under `GAP-001`. |
| `backend/app/models/workflow.py` | none | delete | Standalone global workflows are outside the Workflow Package-only contract. |
| `backend/app/models/capability.py` | none | delete | Global capabilities should remain package-local artifact data only. |
| `backend/app/models/mcp_server.py` | none | delete | Global MCP server persistence is a removed authoring root; package-private MCP config remains artifact data. |
| `backend/app/models/output_schema.py` | none | delete | Global output schemas should remain package-local artifact data only. |
| `backend/app/repositories/agent.py` and matching global authoring repositories | none | delete | Repository support for removed global authoring tables should not be carried forward. |
| `backend/app/schemas/agent.py` and matching global authoring schemas | none | delete | External DTOs for removed global authoring routes should not remain as compatibility ballast. |
| `backend/app/services/legacy_authoring.py` | none | delete | Runtime-blocked helper preserves removed behavior instead of deleting it. |

## Backend Tools, MCP, Memory, And Extensions

| Current path | Target home | Status | Reason |
| --- | --- | --- | --- |
| `backend/app/agents/tool_catalog/server_declared.py` | `backend/app/application/tools/catalog.py` plus extension contributions | split | Tool metadata is read-only application/catalog behavior; extension-owned tool declarations stay extension-owned. |
| `backend/app/agents/runtime_tools/registry.py` | `backend/app/application/tools/dispatch.py` plus `backend/app/ports/runtime_tools.py` | split | Runtime dispatch should be separate from catalog metadata and checked through grants and extension state. |
| `backend/app/agents/mcp/*` | `backend/app/infrastructure/mcp/*` behind package-private MCP ports | move | MCP transport/security is runtime infrastructure, not a global authoring API. |
| `backend/app/api/memory.py` | `backend/app/api/memory.py` | keep in place | Scoped access-context operations remain platform API adapters. |
| `backend/app/schemas/memory.py` | `backend/app/schemas/memory.py` plus memory domain types | split | API projections stay in schemas; scope and grant rules should live in domain. |
| `backend/app/services/memory*` | `backend/app/application/memory/*`, `backend/app/domain/memory/*`, and persistence implementations | split | Memory access must keep package-contextual grants separate from storage details. |
| `backend/app/extensions/registry.py` | `backend/app/extensions/registry.py` | keep in place | Statically resident extension registration is aligned with the target model. |
| `backend/app/services/extension_service.py` | `backend/app/application/extensions/state.py` plus extension state repository port | split | Public slim-state reads and persistence concerns should separate, while registry internals stay private. |
| `backend/app/extensions/signaldeck_finance/*` | `backend/app/extensions/signaldeck_finance/*` | keep in place | Finance remains extension-owned for routes, tools, providers, lifecycle hooks, and report lookup. |
| `backend/app/extensions/signaldeck_digital_oracle/*` | `backend/app/extensions/signaldeck_digital_oracle/*` | keep in place | Digital Oracle remains tool-only with no route or nav surface. |

## Frontend Routes, Extensions, And API Clients

| Current path | Target home | Status | Reason |
| --- | --- | --- | --- |
| `frontend/src/routes.ts` | `frontend/src/routes.ts` | keep in place | The route table already combines explicit platform routes with extension route assembly. |
| `frontend/src/routes.metadata.ts` | `frontend/src/routes.metadata.ts` | keep in place | Route ownership, shell mode, width, nav, and visibility metadata are aligned target contracts. |
| `frontend/src/extensions/runtime-helpers.ts` | `frontend/src/extensions/runtime-helpers.ts` | keep in place | Backend extension state remains the visibility source for routes, nav, and tool filtering. |
| `frontend/src/extensions/registry.ts` | `frontend/src/extensions/registry.ts` | keep in place | Statically resident frontend extension registration matches the extension model. |
| `frontend/src/extensions/signaldeck-finance*` | `frontend/src/extensions/signaldeck-finance*` | keep in place | Finance frontend routes, nav, and tool-prefix discovery remain extension-owned. |
| `frontend/src/extensions/signaldeck-digital-oracle/*` | `frontend/src/extensions/signaldeck-digital-oracle/*` | keep in place | Digital Oracle stays tool-discovery only and contributes no pages or navigation. |
| `frontend/src/pages/workflow-packages/*` | `frontend/src/pages/workflow-packages/*` plus package-local types | split | Page components stay, but any legacy global authoring type imports should be replaced with package-local contracts. |
| `frontend/src/lib/platform-authoring/*` | package-local authoring helpers under the same feature area | rewrite | Helpers should speak Workflow Package artifact concepts directly, not global `AgentRead` or `WorkflowRead`. |
| `frontend/src/lib/api/workflow-packages.ts` | `frontend/src/lib/api/workflow-packages.ts` | keep in place | Typed package manifest, import, export, preflight, launch, and secret-binding API helpers remain package-first client contracts. |
| `frontend/src/hooks/use-workflow-packages.ts` | `frontend/src/hooks/use-workflow-packages.ts` | keep in place | Query/mutation policy stays hook-owned and should continue using extension-filtered tool reads. |
| `frontend/src/pages/workflow-packages/editor.tsx` | route-local workflow-package editor panels | split | Correct package scope, but editor shell, resource editors, validation, and YAML panels should be separated if refactored. |
| `frontend/src/pages/workflow-packages/launch.tsx` | route-local launch/preflight panels | split | Correct package-first launch route, but preflight, runtime inputs, saved inputs, and create-run controls should be route-local subcomponents. |
| `frontend/src/pages/workflow-packages/import-page.tsx` | `frontend/src/pages/workflow-packages/import-page.tsx` | keep in place | Pasted-manifest import remains a dedicated package route surface. |
| `frontend/src/pages/model-connections/editor.tsx` | `frontend/src/pages/model-connections/editor.tsx` | keep in place | Global credential editing is live platform state and must keep secrets write-only. |
| `frontend/src/pages/scheduled-tasks/*` | `frontend/src/pages/scheduled-tasks/*` | keep in place | Package-first automation route family remains platform-owned. |
| `frontend/src/pages/runs/*` | `frontend/src/pages/runs/*` | keep in place | Run console/detail sections remain platform-owned and should stay split by detail sections. |
| `frontend/src/pages/memory/list.tsx` | `frontend/src/pages/memory/list.tsx` plus route-local panels if needed | split | Single `/memory` route remains correct; access-context controls, inspector, revisions, and events can split without child routes. |
| `frontend/src/lib/types/agent.ts` | package-local authoring type modules | rewrite | Still-used type names imply global authoring; target naming should describe package-local agents. |
| `frontend/src/lib/types/workflow.ts` | package-local workflow graph type modules | rewrite | Still-used type names imply standalone workflows; target naming should describe package-local workflow graphs. |
| `frontend/src/lib/platform-authoring/workflows/*` | package-local workflow graph helpers | rewrite | Helpers should emphasize Workflow Package graph authoring, not standalone global workflows. |
