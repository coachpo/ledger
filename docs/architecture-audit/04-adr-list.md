# Target ADR List

This ADR list captures the architecture decisions needed to lock the target architecture before implementation cleanup. It is a backlog, not an implementation plan.

Each ADR should be accepted only when it cites live source evidence, names non-goals, and defines tests or static checks. Removed global authoring surfaces must be deleted directly; no ADR should preserve them through wrappers, adapters, aliases, or compatibility paths.

Primary evidence:

- `00-contract-baseline.md:13-23` for live in-scope boundaries.
- `00-contract-baseline.md:25-36` for explicit out-of-scope boundaries.
- `00-contract-baseline.md:38-60` for architecture and deletion rules.
- `02-current-architecture.md:18-23` for aligned current behavior.
- `03-gap-register.md:29-70` for the gaps this target architecture must resolve.
- `03-gap-summary.md:41-47` for fix-first rationale.

## ADR-001: Package-First Authoring Boundary

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Workflow Packages remain the only executable authoring root. Package-private agents, output schemas, capability profiles, MCP configs, and workflow graphs live inside package artifacts only. |
| Rationale | `00-contract-baseline.md:13`, `00-contract-baseline.md:27`, and `03-gap-register.md:29-37` make global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration-v2, and runtime-v2 removed surfaces. |
| Consequences | Delete retained global ORM, repositories, schemas, frontend wire types, and runtime-blocked helpers that are not needed by package artifacts. Do not create compatibility aliases. |
| Acceptance checks | Removed backend global routes still return not found; package import/validate/launch tests still pass; no live code imports deleted global authoring models outside package artifact parsing. |

## ADR-002: Queued Run Execution Boundary

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Launch, rerun, fork, and schedule-fire flows create queued `Run` records only. Execution starts after `RunSchedulerWorker` claims a lease and passes the claimed run to runtime execution. |
| Rationale | `00-contract-baseline.md:15-16`, `00-contract-baseline.md:40-42`, `02-current-architecture.md:38-49`, and `03-gap-register.md:63-70` define queue-only launch and worker-owned execution. |
| Consequences | API handlers and application use cases may validate, snapshot, enqueue, and return run metadata, but they must not execute package workflows inline. Terminal status ownership is guarded by the S6 active lease-owner finalization contract. |
| Acceptance checks | Launch, rerun, fork, and schedule run-now tests assert queued status and no inline execution; runtime code has no imports from `backend/app/api/*`; stale lease and terminal status behavior is covered or explicitly reviewed. |

## ADR-003: Clean Architecture Dependency Rule

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Backend dependencies point inward: API modules call application use cases; application use cases depend on domain rules and ports; domain modules do not import ports; infrastructure implements ports and may depend on framework, SQLAlchemy, provider SDK, telemetry, and transport details. |
| Rationale | `03-gap-register.md:40-48` and `03-gap-register.md:63-70` show service and persistence boundaries that need separation before more platform behavior lands. |
| Consequences | Existing broad `services` modules should split by use case, domain rule, port, and infrastructure implementation. Domain modules cannot import FastAPI, SQLAlchemy sessions, provider clients, queue/runtime-tool ports, or other infrastructure-facing ports. |
| Acceptance checks | Static import checks prove no import cycles across layers; API modules delegate to use cases/services; runtime modules do not import router modules; domain modules do not import SQLAlchemy sessions, provider SDK clients, or ports. |

## ADR-004: Extension Registry And Gating Model

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Statically resident extensions are the only extension mechanism. Backend and frontend visibility derive from persisted slim extension state: `key`, `label`, and `enabled`. |
| Rationale | `00-contract-baseline.md:18-20`, `00-contract-baseline.md:43-46`, and `02-current-architecture.md:76-84` show Finance and Digital Oracle as bundled extensions with slim public state. |
| Consequences | Extension registrars remain private wiring. Platform routes and frontend metadata do not inspect private registry details. Digital Oracle remains tool-only. Finance-owned routes and tools remain gated by `signaldeck.finance`. |
| Acceptance checks | `/api/extensions` exposes only slim state; frontend route/nav/tool filtering uses backend extension state; Digital Oracle has no route or nav contribution; Finance route tests prove disabled-state gating. |

## ADR-005: PostgreSQL-Backed Run Queue

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | PostgreSQL remains the source of truth and initial queue for Workflow Package runs, schedule fires, queue leases, heartbeat state, and stale recovery. |
| Rationale | `00-contract-baseline.md:15-16`, `02-current-architecture.md:42-49`, and `03-gap-register.md:63-70` define the current queue and worker model. |
| Consequences | Do not introduce a separate broker as an implied requirement. Queue improvements should first harden claim, heartbeat, release, stale recovery, and terminal status ownership in the existing PostgreSQL-backed model. |
| Acceptance checks | Queue claim, heartbeat, release, stale recovery, and terminal status tests cover the reviewed ownership contract; no raw cron or external queue SLA claims are introduced. |

## ADR-006: Clean Migration Baseline And Startup Repair

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Startup repair remains code-owned in `backend/app/db/` or its infrastructure successor, but only for live tables and live invariants. Retired-surface cleanup is deleted under the no-users baseline. |
| Rationale | `00-contract-baseline.md:50`, `00-contract-baseline.md:56-57`, `02-current-architecture.md:101-106`, and `03-gap-register.md:40-48` separate live PostgreSQL repair from speculative migration ballast. |
| Consequences | Keep repairs for runs, schedules, extension state, model connections, package secrets, runtime inputs, and memory. Remove repair paths for global authoring tables, legacy skill storage, Studio, Tryout, orchestration-v2, and runtime-v2. |
| Acceptance checks | Startup repair tests cover only live tables and invariants; route/table absence checks prove removed surfaces are not live contracts; no test requires preserving global authoring or legacy skill storage cleanup. |

## ADR-007: Scoped Memory Only

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Memory remains platform-core, explicit-scope, package-contextual, and grant-aware. There is no public global memory CRUD or unscoped search surface. |
| Rationale | `00-contract-baseline.md:21`, `00-contract-baseline.md:29`, `00-contract-baseline.md:47`, and `02-current-architecture.md:72-74` define scoped memory and reject unscoped memory assumptions. |
| Consequences | Memory APIs and tools require an access context. Model-visible, API-visible, and UI-visible projections remain separate. Report history remains Finance/report-owned history, not canonical memory storage. |
| Acceptance checks | `/api/memory` remains access-context POST operations; `signaldeck.memory.write` and `signaldeck.memory.lookup` stay platform-owned; tests cover scoped grants and no unscoped search. |

## ADR-008: Legacy Route Removal Policy

| Field | Content |
| --- | --- |
| Status | Proposed |
| Decision | Removed global authoring and retired runtime surfaces stay deleted. Missing routes return not found; no compatibility aliases, redirects, wrappers, or hidden pages are added. |
| Rationale | `00-contract-baseline.md:27-31`, `00-contract-baseline.md:52-60`, `02-current-architecture.md:31`, and `03-gap-register.md:29-37` define removed surfaces as deletion targets rather than compatibility contracts. |
| Consequences | Cleanup may delete retained global authoring models, repositories, schemas, frontend wire types, and blocked helpers. Tests should preserve absence guarantees, not old route behavior. |
| Acceptance checks | Backend removed-route tests pass as 404/not-found; frontend removed-route tests pass as 404/not-found; docs mention retired surfaces only as non-goals, removed routes, or deletion targets. |

## ADR Acceptance Checklist

- Each ADR cites repo-local evidence and names non-goals.
- No ADR introduces auth, tenancy, raw cron, queue SLA promises, Digital Oracle pages, global memory CRUD, or long-term draft import/export compatibility.
- No ADR preserves removed global authoring APIs through aliases, wrappers, shims, or adapters.
- Each accepted ADR adds or updates tests/static checks for its boundary.
