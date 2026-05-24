# Data Model Design

> Status: Live data-model reference for branch `main` at `adc9887`.

## Overview

SignalDeck uses PostgreSQL for the Finance Workspace, templates, reports, package-first platform artifacts, runs, package secrets, and platform-core memory. Startup schema repair lives in `backend/app/db/`; Alembic scaffolding is not the live upgrade authority.

The data model follows two boundaries. Finance-owned product tables support preserved portfolio, template, report, and market-data behavior. Platform-owned tables support Workflow Packages, Model Connections, bundled extension state, package secret bindings, Tools metadata references, Runs, run operation evidence, run fork lineage, and memory entries/revisions/events.

## Preserved Finance Product Tables

| Table | Role |
|---|---|
| `portfolios` | Isolated workspaces with slug, name, description, base currency, and timestamps. |
| `balances` | Portfolio-scoped deposit/withdrawal cash rows with non-negative amounts. |
| `positions` | Aggregate holdings keyed by `(portfolio_id, symbol)`. |
| `trading_operations` | Append-only BUY, SELL, DIVIDEND, and SPLIT history with balance-label snapshots. |
| `market_quotes` | Rebuildable quote cache keyed by provider, symbol, and `as_of`. |
| `symbol_name_cache` | Rebuildable symbol display-name cache. |
| `text_templates` | Global reusable template documents. |
| `reports` | Markdown snapshots keyed by unique `name` and `slug` with source and JSONB metadata. |

## Platform Tables

| Table | Role |
|---|---|
| `workflow_packages` | One mutable current package per stable key, including manifest source, package definition, compiled plan, hashes, dependency keys, and timestamps. Live package rows do not store lifecycle status. |
| `workflow_package_secret_bindings` | Package-local encrypted secret values keyed by package and binding key; reads expose only presence/timestamps, never raw values. |
| `run_workflow_package_snapshots` | One immutable executable package snapshot per run, including copied package identity, workflow identity, hashes, manifest/export material, compiled plan, launch inputs, resolved non-secret model runtime profiles, and preflight summary. |
| `model_connections` | Global saved provider/model endpoint config, selected `protocol_profile`, capability-status JSONB, policy fields, probe cache metadata, encrypted API keys, reachability-test metadata, and archive state. |
| `extension_states` | Operational bundled-extension state keyed by `extension_key`, storing only `enabled`. |
| `runs` | Global persisted package execution input/output, lifecycle state, progress/queue source data, scheduler lane and lease metadata, totals, optional trace ids, rerun metadata, historical replay lineage, package provenance, and dependency-only extension requirements. |
| `run_forks` | First-class runtime fork artifact for descendant runs, keyed by `run_id`, with source run lineage, source invocation id, source/resume step indexes, and edited invocation input. |
| `run_steps` | Persisted workflow step status, copied rerun/fork context, graph metadata, errors, and timestamps. |
| `run_agent_invocations` | Persisted agent invocation lineage, resolved inputs, outputs, token usage, durations, optional span ids, copied context, and edited fork target provenance. |
| `run_operation_invocations` | Persisted non-agent operation invocation lineage for `kind: http`, redacted request metadata, bounded response metadata, outputs, errors, optional span ids, and copied context. |
| `agent_memory_entries` | Canonical platform-core memory entries keyed by opaque `memory_id`, with package-qualified scope, kind, subject refs, status, content hash, idempotency key, and trusted provenance. |
| `agent_memory_revisions` | Immutable content revisions keyed by opaque `revision_id`, with model-safe summary/content, attributes, revision action, supersession links, and content hash. |
| `run_memory_events` | Append-only run-scoped memory evidence for retrieval, injection, writes/reuse, supersession, review, and failure facts. |

Package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes are stored inside the current package artifact. Runs copy the executable artifact into their own snapshot at launch. These resources are not normalized into global authoring tables.

## Integrity Rules

- Money, quantities, and market values stay decimal-safe and cross the API as strings.
- Portfolio-owned records enforce portfolio isolation through foreign keys and service lookups.
- Trading operations are append-only; full sell-down may delete the current aggregate position row.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content updates are allowed. `source` values are `compiled`, `uploaded`, `external`, and `agent`; `external` is for true external user/API-created reports, not agent-created reports.
- Workflow packages are mutable current definitions without a live status lifecycle. They store dependency keys as artifact references; current readiness is evaluated separately against live model connections, extension state, and package secret bindings.
- Package exports keep private MCP `env`, `headers`, and `query` values inline while omitting database ids, run history, package secret binding rows, and raw package secret binding values.
- Package secret binding values remain encrypted at rest, are never exported, and are never echoed in reads, diagnostics, compiled graph refs, run details, or logs.
- Model-connection secrets remain encrypted at rest and masked in reads/errors. Workflow package manifests store model connection keys as live bindings, not provider credentials.
- `protocol_profile` is constrained to `openai_chat_completions` or `openai_responses`; `capabilities` stores public capability statuses of `supported`, `unsupported`, `unknown`, or `notApplicable`.
- Model-connection policy columns store output strategy, parallel tool-call, reasoning, and streaming defaults.
- Runs copy the effective non-secret model runtime profile into package provenance at launch. Raw key material stays in the live Model Connection secret payload.
- Global tools are read-only server-declared metadata, exposed by API and referenced by package-local capability profiles. Disabled extension-owned tools stay out of `/api/tools`, while platform-core memory tools stay visible independent of finance extension state.
- Public extension state is not a manifest metadata store. It is the `extension_states` key plus `enabled` flag, surfaced as `key`, `label`, and `enabled` through `/api/extensions`.
- Runs store snapshot-based package id, package key, package hashes, workflow key, local resource refs, resolved model connection refs, launch inputs, and `extension_dependencies` records containing only extension key, surfaces, and fields.
- Runs store scheduler metadata such as execution scope key, concurrency policy, lease owner/timestamps, attempt count, queued time, and last claimed time. Queue read models derive from persisted scheduler state. Progress read models derive from persisted invocation statuses.
- Reruns may edit root launch parameters. Forks preserve source run input, copy upstream context, persist one `run_forks` artifact, and mark the selected target agent invocation as edited with source invocation provenance. `resume_step_index` is the execution boundary only.
- Runtime request metadata for HTTP operations must redact sensitive URL query names and all secret-backed headers, query fields, and body fields. Response metadata is bounded and stores redaction-safe URL, status, selected headers, content type, body preview, byte count, hash, and redirect metadata.
- Shared memory writes canonicalize package, workflow, and agent broader scopes before storage. Shared-scope revision mutations use row-level conflict control and return retryable `memory_revision_conflict` errors instead of allowing competing winners.
- Startup repair handles current platform tables through `backend/app/db/upgrades.py`; repair must not recreate package-side history or treat report rows as canonical memory.

## Retired Data

Backtest, simulation, orchestration, Studio, Tryout, runtime-v2, skill-contract tables, and removed global authoring tables for agents, capabilities, MCP servers, output schemas, and workflows are not part of the current shipped data contract.
