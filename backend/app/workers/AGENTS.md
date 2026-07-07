# BACKEND WORKERS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers long-lived worker entrypoints in `app/workers/`.

## OVERVIEW
`app/workers/` owns the out-of-request execution loop for package automation. The current worker surface is the scheduler in `run_scheduler.py`, which materializes due Scheduled Task fires into queued Workflow Package runs, claims queued runs, maintains leases and heartbeats, recovers stale leases, resolves the enabled execution-provider bundle, and hands execution to `RunService`.

The worker is platform-core runtime infrastructure. It is not a finance route surface and it is not a browser-facing scheduler product.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Scheduler entrypoint | `run_scheduler.py` | `main()`, `RunSchedulerWorker`, advisory lock, due-schedule materialization, claim loop, heartbeats, and lease release |
| Due schedule materialization | `../services/workflow_package_schedule_materializer.py`, `../services/workflow_package_schedule_service.py` | finds eligible schedules, renders scheduled inputs, records fires, and queues ordinary runs |
| Queue semantics | `../services/run_queue_service.py` | claim, heartbeat, stale-lease recovery, and release rules |
| Run execution handoff | `../services/run_service.py` | executes claimed runs after the worker obtains a lease |
| Extension-aware providers | `../services/extension_service.py` | resolves the enabled execution-provider bundle before execution |
| Runtime settings | `../core/config.py` | worker concurrency, poll interval, heartbeat, and lease TTL settings |

## CONVENTIONS
- Keep worker startup explicit: `main()` initializes the database, then runs `RunSchedulerWorker().run_forever()`.
- Only one worker process may hold the scheduler advisory lock at a time.
- Due Scheduled Task materialization runs through `WorkflowPackageScheduleMaterializer` before run execution; the worker should not inline recurrence math or scheduled-input rendering.
- Queue claiming, lease heartbeats, stale-lease recovery, and lease release stay in `RunQueueService`; do not fork that logic in the worker.
- The worker resolves the execution-provider bundle through `ExtensionService` at execution time so extension state stays live.
- `run_forever()` owns the long-lived polling loop; `run_once()` is the bounded helper for tests and targeted execution.
- Scheduler threads execute claimed runs concurrently up to `run_scheduler_max_active_runs`; heartbeat threads must stop and release leases even on failure.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not execute queued runs from API request handlers.
- Do not bypass the advisory lock, lease heartbeat, or stale-lease recovery rules.
- Do not hard-code concurrency, poll, heartbeat, or TTL values outside settings.
- Do not resolve finance/provider/runtime ownership directly in the worker when `ExtensionService` already owns that boundary.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_db_bootstrap.py
```
