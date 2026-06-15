# Contract Baseline

This baseline turns the current requirement set into audit rules. It is grounded in these repo-local inputs:

- `docs/requirements/reverse-requirements.md`
- `docs/requirements/traceability-matrix.md`
- `docs/requirements/open-questions.md`

The requested filenames exist at those paths. `open-questions.md` states that there are no remaining true open questions for the current baseline.

## In-Scope Product Boundaries

- Workflow Packages are the only live executable workflow authoring root.
- Platform APIs under `/api` own workflow packages, schedules, model connections, extensions, tools, memory, and runs.
- Launch and descendant flows create durable queued Runs. Request handlers may validate and persist launch intent, but they must not execute workflow packages inline.
- The scheduler worker materializes due Scheduled Tasks into ordinary queued runs, claims queued runs, maintains leases, recovers stale leases, and executes claimed runs.
- Platform core owns workflow package artifacts, launch/preflight/runtime-input flow, schedules, runs, model connections, tool metadata and dispatch infrastructure, memory, extension state, and runtime infrastructure.
- `signaldeck.finance` is an extension-owned bounded context for preserved Finance Workspace routes, providers, tools, report lookup, and finance-owned runtime behavior.
- `signaldeck.digital_oracle` is tool-only. It owns prediction markets, SEC filings, and market sentiment tools only.
- Public extension state is slim: `key`, `label`, and `enabled`.
- Memory is platform-core, explicit-scope, package-contextual, and grant-aware.
- Model-connection and package secrets are write-only on public reads and encrypted at rest.
- External API conventions are camelCase fields, string decimals, UTC timestamps, and shared `{code, message, details[]}` error envelopes.

## Explicit Out-of-Scope Boundaries

- Legacy/global authoring roots outside Workflow Packages: global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration-v2, runtime-v2, and `/skills*`.
- Digital Oracle routes, pages, navigation groups, provider bundles, lifecycle hooks, or finance behavior.
- Public global memory CRUD, unscoped memory search, report-backed memory storage, or vector retrieval requirements.
- Multi-user authentication, authorization, tenancy, account management, or role enforcement.
- Long-term Workflow Package import/export compatibility beyond the current live contract.
- Raw cron scheduling and client-owned recurrence math.
- User-facing queue latency, throughput, or execution-time SLA guarantees.
- Live broker execution, realtime market streaming, or autonomous trading.
- Formal WCAG certification, localization, multilingual UI, or privacy/regulatory programs beyond current technical controls.
- Dashboard analytics beyond the narrow landing-header and retry behavior in the baseline.

## Non-Negotiable Architecture Rules

- Keep package execution package-first. A new executable workflow path must be inside a Workflow Package or it is out of contract.
- Keep API launch/rerun/fork paths queue-only. Execution belongs to `RunSchedulerWorker`, `RunQueueService`, and `RunService.execute_claimed_run` after a lease is claimed.
- Keep recurrence and schedule-fire semantics backend-owned. Scheduled Tasks use structured recurrence, IANA timezones, scheduled input templates, previews, fires, and queued run provenance.
- Keep platform-core and extension-owned behavior separate. Promote extension behavior into core only after an explicit shared-contract decision and matching docs/tests.
- Keep Finance-owned routes and tools behind `signaldeck.finance` state gates.
- Keep Digital Oracle tool-only. It may contribute server-declared/runtime tools, but no route or nav surface.
- Keep `/api/extensions` and frontend extension reads limited to `key`, `label`, and `enabled`.
- Keep memory access scoped by package context, concrete private scope, and server-derived grants.
- Keep secrets encrypted at rest and absent from public reads, exports, run detail, operation detail, and user-facing diagnostics.
- Keep API shape centralized through `CamelModel`, shared formatting helpers, and FastAPI error handlers rather than hand-built payloads.
- Keep PostgreSQL startup repair in `backend/app/db/`; Alembic scaffolds, docs, and cache/build output are not schema authority.

## Delete, Do Not Preserve

- Delete legacy/global authoring paths instead of aliasing or wrapping them.
- Delete Studio, Tryout, orchestration-v2, runtime-v2, `/skills*`, simulations, backtests, and removed route families from live acceptance paths.
- Delete compatibility shims for unreleased draft shapes unless an authoritative requirement names the old path as a live contract.
- Delete speculative migration ballast for product surfaces that have no users and no release contract.
- Delete finance leakage from platform-core contracts unless the shared platform behavior is intentionally defined.
- Delete Digital Oracle route/nav assumptions; preserve only the three tool keys and OpenAI function names named by the baseline.
- Delete unscoped memory assumptions; mark them `needs code evidence` if a future audit cannot prove package-contextual, scope-bound access.
