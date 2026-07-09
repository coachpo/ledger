# Data Model

SignalDeck uses PostgreSQL for the mini-Jenkins runtime: finance
templates/reports, Workflow Package artifacts, schedules, model connections,
runs, run evidence, and encrypted package secrets. The live schema is created by
`backend/app/db/` with SQLAlchemy `create_all`; schema changes require rebuilding
the database.

## Finance Tables

| Table | Role |
| --- | --- |
| `text_templates` | Reusable markdown template documents for preserved report workflows. |
| `reports` | Markdown report snapshots keyed by unique `name` and `slug`, with source and JSON metadata. |
| `market_quotes` | Rebuildable market quote cache keyed by provider, symbol, and `as_of`. |
| `symbol_name_cache` | Rebuildable symbol display-name cache. |

## Platform Tables

| Table | Role |
| --- | --- |
| `workflow_packages` | Mutable current package per stable key, storing manifest source, package definition, compiled plan, hashes, extension dependency surfaces, and timestamps. |
| `workflow_package_secret_bindings` | Package-local encrypted secret values keyed by package and binding key; reads expose only presence/timestamps. |
| `workflow_package_schedules` | Recurring Workflow Package schedule definitions with package/workflow target, enabled or paused status, recurrence, timezone, policies, next fire, input template, and template vars. |
| `workflow_package_schedule_fires` | Schedule-owned fire rows for scheduled or manual occurrences, rendered parameters, local scheduled fields, status, and skip/error data; linked runs point back through `runs.schedule_fire_id` while the schedule exists. |
| `model_connections` | Global provider/model bindings with selected `protocol_profile`, endpoint/model settings, encrypted API key, capability/policy/probe/test metadata, and timestamps. |
| `runs` | Queued and executed Workflow Package runs with lifecycle state, canonical inputs/output, queue/progress data, scheduler lane/lease metadata, cancel metadata, totals, optional trace ids, rerun link, package provenance, schedule provenance, and extension dependencies. |
| `run_workflow_package_snapshots` | Immutable executable package snapshot per run, including copied package identity, workflow identity, hashes, safe manifest export material, executable compiled plan, launch inputs, non-secret runtime profiles, and preflight summary. |
| `run_steps` | Planned workflow node status, origin, graph metadata, step-level error text, and timestamps. |
| `run_agent_invocations` | Agent invocation identity, input mode, wiring, resolved input and input origin, outputs, error code/message/details, token usage, duration, and optional span ids. |
| `run_operation_invocations` | HTTP operation invocation identity, redacted request metadata, bounded response metadata, outputs, error code/message/details, duration, and optional span ids. |

Package-local agents, output schemas, capability profiles, private MCP configs,
HTTP operation nodes, and workflow graphs are stored inside package artifacts,
not normalized into global authoring tables. Runs copy executable artifacts into
run-owned snapshots at launch.

## Integrity Rules

- Backend JSON is camelCase externally and snake_case internally.
- Money, quantities, and market values cross API boundaries as decimal-safe strings.
- Error envelopes are `{code, message, details[]}` for API-owned errors.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content changes.
- Report sources are `compiled`, `uploaded`, `external`, and `agent`.
- Workflow Packages store dependency keys as artifact refs; readiness is evaluated against live Model Connections, installed extension tools, and package secret bindings.
- Manifest source/package-definition payloads returned by manifest reads, exports, and run provenance omit secret-bearing private MCP `env`, `headers`, and `query`, database ids, run history, package secret binding rows, and raw package secret values; API envelopes can still include package identity such as `packageId` and `packageKey`.
- Package secret binding values and Model Connection API keys are encrypted at rest and never returned in reads, exports, run details, logs, diagnostics, or metadata.
- Run provenance redacts package-private MCP `env`, `headers`, and `query` values from compiled-plan reads.
- Model Connection `protocol_profile` is the persisted runtime selector; backend services own capability evidence, policy columns, probe cache metadata, and reachability-test metadata.
- Tools are read-only server-declared metadata from static extensions and are referenced by package-local capability profiles.
- Runs store immutable package provenance, scheduler metadata, run-owned schedule provenance, queue/progress source data, typed failure metadata, bounded `toolCallRetries`, and distinct `providerRetries` for transient provider create-call retries.
- Run statuses are `queued`, `running`, `succeeded`, `failed`, and `cancelled`.
- Retention deletes only terminal runs with `finished_at` older than `SIGNALDECK_RUN_RETENTION_DAYS`.
- HTTP operation request metadata redacts sensitive query names and all secret-backed headers, query fields, and body fields. Response metadata is bounded and redaction-safe.
- Deleting a schedule deletes schedule-owned fire rows and stops future automation, but existing runs remain readable through run-owned schedule provenance.
- Deleting a Workflow Package deletes its owned runs.
- Reruns store only a source-run link and may edit root launch parameters.

## Schema Boundary

Only the tables listed above are part of the shipped data contract. Any removed
or retired surface stays out of this data-model owner unless live code
reintroduces it.
