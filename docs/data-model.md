# Data Model Design

> Status: Live data-model reference for branch `main` at `e2c635f`.

## Overview

SignalDeck uses PostgreSQL for preserved portfolio/report/template data and the package-first agent-platform tables. Startup schema repair lives in `backend/app/db/`; Alembic scaffolding is not the live upgrade authority.

## Preserved Product Tables

| Table | Role |
|---|---|
| `portfolios` | isolated workspaces with slug, name, description, base currency, timestamps |
| `balances` | portfolio-scoped deposit/withdrawal cash rows with non-negative amounts |
| `positions` | aggregate holdings keyed by `(portfolio_id, symbol)` |
| `trading_operations` | append-only BUY/SELL/DIVIDEND/SPLIT history with balance-label snapshots |
| `market_quotes` | rebuildable quote cache keyed by provider, symbol, and `as_of` |
| `symbol_name_cache` | rebuildable symbol display-name cache |
| `text_templates` | global reusable template documents |
| `reports` | markdown snapshots keyed by unique `name` and `slug` with JSONB metadata |

## Agent-Platform Tables

| Table | Role |
|---|---|
| `workflow_packages` | one mutable current package per stable key, including name, description, manifest source, package definition, compiled plan, hashes, extension dependencies, and timestamps. Live package rows do not store lifecycle status. |
| `run_workflow_package_snapshots` | one immutable executable snapshot per workflow-package run, keyed by `run_id`, with copied package identity, nullable historical `workflow_package_status`, workflow identity, hashes, manifest/export material, compiled plan, local refs, launch inputs, model-connection audit refs, and preflight summary |
| `model_connections` | global saved provider/model endpoint config, encrypted API keys, health/test metadata, and archive state |
| `extension_states` | operational bundled-extension state keyed by `extension_key`, storing only `enabled` |
| `runs` | global persisted package execution input/output, status, totals, optional Logfire trace ids, rerun metadata, read-only historical replay lineage, package provenance, launch snapshots, and dependency-only extension requirements |
| `run_forks` | first-class runtime fork artifact for descendant runs, keyed by `run_id`, with source run lineage, source invocation id, source and resume step indexes, and the edited invocation input snapshot |
| `run_steps` | persisted workflow step status, copied rerun/fork context, graph metadata, errors, and timestamps |
| `run_agent_invocations` | persisted agent invocation lineage, resolved inputs, outputs, token usage, durations, optional trace span ids, copied context, and edited fork target provenance |
| `run_operation_invocations` | persisted non-agent operation invocation lineage for `kind: http`, redacted request metadata, bounded response metadata, outputs, errors, optional trace span ids, and copied context |
| `agent_memory_entries` | canonical platform-core memory entries keyed by opaque `memory_id`, with scope, kind, subject refs, status, content hash, idempotency key, and trusted provenance |
| `agent_memory_revisions` | immutable content revisions keyed by opaque `revision_id`, with model-safe summary/content, attributes, revision action, supersession links, and content hash |
| `run_memory_events` | append-only run-scoped memory evidence for retrieval, injection, writes/reuse, supersession, review, and failure facts |

Package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes are stored inside the current package artifact. Runs copy the executable artifact into their own snapshot at launch. These resources are not normalized into global authoring tables.

## Integrity Rules

- Money, quantities, and market values stay decimal-safe and cross the API as strings.
- Portfolio-owned records enforce portfolio isolation through foreign keys and service lookups.
- Trading operations are append-only; full sell-down may delete the current aggregate position row.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content updates are allowed. `source` describes origin with canonical values `compiled`, `uploaded`, `external`, and `agent`; `external` is for true external user/API-created reports, not agent-created reports.
- Workflow packages are mutable current definitions without a live status lifecycle. Each launch writes one immutable run-owned executable snapshot, and package deletion deletes owned runs with their snapshots. Package exports keep private MCP `env`, `headers`, and `query` values inline while omitting database ids and run history.
- Model-connection secrets remain encrypted at rest and masked in reads/errors. Workflow package manifests store model connection keys as live bindings, not provider credentials. Deletion is blocked by current package bindings, not historical run snapshots.
- Global tools are read-only server-declared metadata, exposed by API and referenced by package-local capability profiles. Disabled extension-owned tools stay out of `/api/tools`, while platform-core memory tools stay visible independent of finance extension state.
- Public extension state is not a manifest metadata store. It is the `extension_states` key plus `enabled` flag, surfaced as `key`, `label`, and `enabled` through `/api/extensions`.
- Runs store snapshot-based package id, package key, package hashes, workflow key, local resource refs, resolved model connection refs, launch inputs, and `extension_dependencies` records containing only extension key, surfaces, and fields. Run provenance may include nullable `workflowPackageStatus` only as historical snapshot data; it is not live package state.
- Reruns may edit root launch parameters. Forks must preserve source run input, copy upstream context, persist one `run_forks` artifact, and mark the selected target agent invocation as edited with source invocation provenance. `resume_step_index` is the execution boundary only; `source_invocation_id` identifies the editable target.
- Historical step replay lineage fields remain readable on old run rows for audit context, but they are not the live write-side artifact for new forks.
- Startup repair handles current platform tables through `backend/app/db/upgrades.py`, including `workflow_packages`, `run_workflow_package_snapshots`, `extension_states`, `runs`, `run_forks`, `run_steps`, `run_agent_invocations`, `run_operation_invocations`, `agent_memory_entries`, `agent_memory_revisions`, and `run_memory_events`. Repair must not recreate package-side history or treat report rows as canonical memory.

## Retired Data

Backtest, simulation, orchestration, Studio, Tryout, runtime-v2, skill-contract tables, and removed global authoring tables for agents, capabilities, MCP servers, output schemas, and workflows are not part of the current shipped data contract. Do not reintroduce them as live schema documentation targets.
