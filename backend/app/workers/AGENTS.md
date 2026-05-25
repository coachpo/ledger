# BACKEND WORKERS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers long-lived worker entrypoints in `app/workers/`.

## OVERVIEW
`app/workers/` owns the out-of-request execution loop for queued Workflow Package runs. The current worker surface is the scheduler in `run_scheduler.py`, which claims queued runs, maintains leases and heartbeats, recovers stale leases, resolves the enabled execution-provider bundle, and hands execution to `RunService`.

The worker is platform-core runtime infrastructure. It is not a finance route surface and it is not a browser-facing scheduler product.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Scheduler entrypoint | `run_scheduler.py` | `main()`, `RunSchedulerWorker`, advisory lock, claim loop, heartbeats, and lease release |
| Queue semantics | `../services/run_queue_service.py` | claim, heartbeat, stale-lease recovery, and release rules |
| Run execution handoff | `../services/run_service.py` | executes claimed runs after the worker obtains a lease |
| Extension-aware providers | `../services/extension_service.py` | resolves the enabled execution-provider bundle before execution |
| Runtime settings | `../core/config.py` | worker concurrency, poll interval, heartbeat, and lease TTL settings |

## CONVENTIONS
- Keep worker startup explicit: `main()` initializes the database, then runs `RunSchedulerWorker().run_forever()`.
- Only one worker process may hold the scheduler advisory lock at a time.
- Queue claiming, lease heartbeats, stale-lease recovery, and lease release stay in `RunQueueService`; do not fork that logic in the worker.
- The worker resolves the execution-provider bundle through `ExtensionService` at execution time so extension state stays live.
- `run_forever()` owns the long-lived polling loop; `run_once()` is the bounded helper for tests and targeted execution.
- Scheduler threads execute claimed runs concurrently up to `run_scheduler_max_active_runs`; heartbeat threads must stop and release leases even on failure.

## ANTI-PATTERNS
- Do not execute queued runs from API request handlers.
- Do not bypass the advisory lock, lease heartbeat, or stale-lease recovery rules.
- Do not hard-code concurrency, poll, heartbeat, or TTL values outside settings.
- Do not resolve finance/provider/runtime ownership directly in the worker when `ExtensionService` already owns that boundary.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_workflow_package_runtime_api.py tests/test_workflow_package_run_contracts.py tests/test_runtime_db_upgrades.py
```
