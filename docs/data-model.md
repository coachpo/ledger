# Data Model Design

> Status: Live data-model reference for the current branch.

## Overview

SignalDeck uses PostgreSQL for finance templates/reports, package-first platform artifacts, runs, and package secrets. Startup bootstrap lives in `backend/app/db/`; there is no live Alembic path.

The data model follows two boundaries. Finance-owned product tables support preserved template, report, and rebuildable market-data cache behavior. Platform-owned tables support Workflow Packages, Model Connections, bundled extension state, package secret bindings, Tools metadata references, Runs, run operation evidence, and typed failure and retry metadata.

## Preserved Finance Product Tables

| Table               | Role                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------ |
| `market_quotes`     | Rebuildable quote cache keyed by provider, symbol, and `as_of`.                      |
| `symbol_name_cache` | Rebuildable symbol display-name cache.                                               |
| `text_templates`    | Global reusable template documents.                                                  |
| `reports`           | Markdown snapshots keyed by unique `name` and `slug` with source and JSONB metadata. |

## Platform Tables

| Table                              | Role                                                                                                                                                                                                                                                                                                                                    |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `workflow_packages`                | One mutable current package per stable key, including manifest source, package definition, compiled plan, hashes, dependency keys, and timestamps. Live package rows do not store lifecycle status.                                                                                                                                     |
| `workflow_package_secret_bindings` | Package-local encrypted secret values keyed by package and binding key; reads expose only presence/timestamps, never raw values.                                                                                                                                                                                                        |
| `workflow_package_schedules`       | Platform-owned recurring Workflow Package schedule definitions with package/workflow target, enabled or paused status, recurrence, timezone, policies, server-owned next-fire timing, and JSON input template data. Schedule deletion removes this row and stops future automation.                                                        |
| `workflow_package_schedule_fires`  | Schedule-owned fire history for materialized scheduled or manual occurrences, including linked run provenance, rendered parameters, local scheduled fields, skip/error data, and status while the owning schedule exists. Fire rows are deleted with their schedule and are not a preserved live surface.                                  |
| `run_workflow_package_snapshots`   | One immutable executable package snapshot per run, including copied package identity, workflow identity, hashes, manifest/export material, compiled plan, launch inputs, approved non-secret model runtime profiles, and preflight summary.                                                                                             |
| `model_connections`                | Global saved provider/model endpoint config, selected `protocol_profile`, backend-owned capability-status JSONB, policy fields, probe cache metadata, encrypted API keys, and reachability-test metadata. Public writes select protocol and endpoint settings only; capability and runtime-profile truth is approved by backend services. |
| `extension_states`                 | Operational bundled-extension state keyed by `extension_key`, storing only `enabled`.                                                                                                                                                                                                                                                   |
| `runs`                             | Global persisted package execution input/output, lifecycle state, progress/queue source data, scheduler lane and lease metadata, totals, optional trace ids, rerun metadata, package provenance, and dependency-only extension requirements.                                                                 |
| `run_steps`                        | Persisted workflow step status, graph metadata, typed tool-failure taxonomy, bounded retry metadata, errors, and timestamps.                                                                                                                                                                                                            |
| `run_agent_invocations`            | Persisted agent invocation identity, approved inputs, outputs, token usage, durations, and optional span ids.                                                                                                                                                                                                                           |
| `run_operation_invocations`        | Persisted non-agent operation invocation identity for `kind: http`, redacted request metadata, bounded response metadata, outputs, errors, and optional span ids.                                                                                                                                                                       |
Package-private agents, output schemas, capability profiles, private MCP configs, workflow graphs, and HTTP operation nodes are stored inside the current package artifact. Runs copy the executable artifact into their own snapshot at launch. These resources are not normalized into global authoring tables.

## Integrity Rules

- Money, quantities, and market values stay decimal-safe and cross the API as strings.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content updates are allowed. `source` values are `compiled`, `uploaded`, `external`, and `agent`; `external` is for true external user/API-created reports, not agent-created reports.
- Workflow packages are mutable current definitions without a live status lifecycle. They store dependency keys as artifact references; current readiness is evaluated separately against live model connections, extension state, and package secret bindings.
- Package exports and browser-visible manifest reads omit secret-bearing private MCP `env`, `headers`, and `query` values while omitting database ids, run history, package secret binding rows, and raw package secret binding values.
- Package secret binding values remain encrypted at rest, are never exported, and are never echoed in reads, diagnostics, compiled graph refs, run details, or logs.
- Model-connection secrets remain encrypted at rest and masked in reads/errors. Workflow package manifests store model connection keys as live bindings, not provider credentials.
- `protocol_profile` is constrained to `openai_chat_completions` or `openai_responses` and remains the canonical persisted runtime selector.
- `capabilities`, policy columns, probe TTL, probe timestamps, and test metadata store backend-owned capability evidence. Public write DTOs must not treat those columns as client-authored truth.
- Model-connection policy columns store output strategy, parallel tool-call, reasoning, and streaming defaults derived and maintained by backend resolution services.
- Runs copy the effective non-secret `ModelConnectionRuntimeProfile` profile into package provenance at launch. Raw key material stays in the live Model Connection secret payload.
- Global tools are read-only server-declared metadata, exposed by API and referenced by package-local capability profiles. Disabled extension-owned tools stay out of `/api/tools`; there is no server-declared memory tool surface.
- Public extension state is not a manifest metadata store. It is the `extension_states` key plus `enabled` flag, surfaced as `key`, `label`, and `enabled` through `/api/extensions`.
- Runs store snapshot-based package id, package key, package hashes, workflow key, local resource refs, approved model connection refs, launch inputs, and `extension_dependencies` records containing only extension key, surfaces, and fields.
- Runs store scheduler metadata such as execution scope key, concurrency policy, lease owner/timestamps, attempt count, queued time, and last claimed time. Queue read models derive from persisted scheduler state. Progress read models derive from persisted invocation statuses.
- Deleting a schedule deletes its schedule-owned fire rows, stops future automation, preserves existing run history, and keeps direct run artifacts readable through run-owned `scheduleProvenance`. Reruns store only a source-run link and stay independent of schedule ownership.
- Workflow Package deletion semantics are unchanged: deleting a package still deletes its owned runs.
- Runtime failure metadata stores typed `failureTaxonomy` records, bounded `toolCallRetries` evidence, and distinct live-execution `providerRetries` evidence without raw tool arguments, secrets, headers, or provider bodies. `toolCallRetries` covers the model-feedback correction path for typed tool-call argument failures. `providerRetries` lives under `graphMetadata.modelGateway.providerRetries` for transient provider create-call retries only, uses `policy="transientProviderRetry/v1"` and `maxAttempts=3`, records failed attempts only, omits the field on first-attempt success and first non-retryable failure, and includes `terminalOutcome` only for `succeededAfterRetry` or `exhausted`. Connection tests, capability probes, and Responses manual replay do not persist provider retry metadata.
- Reruns may edit root launch parameters.
- Runtime request metadata for HTTP operations must redact sensitive URL query names and all secret-backed headers, query fields, and body fields. Response metadata is bounded and stores redaction-safe URL, status, selected headers, content type, body preview, byte count, hash, and redirect metadata.
- Startup bootstrap uses SQLAlchemy `create_all`, bundled package seeds, and stale-run recovery in `backend/app/db/`; report rows remain report-domain history.

## Retired Data

Backtest, simulation, orchestration, Studio, Tryout, runtime-v2, skill-contract tables, workflow-memory/checkpoint tables, invocation-input descendant tables, and global authoring tables for agents, capabilities, MCP servers, output schemas, and workflows are not part of the current shipped data contract.
