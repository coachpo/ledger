# Data Model Design

> Status: Live data-model reference as of 2026-05-08.

## Overview

Ledger uses PostgreSQL for preserved portfolio/report/template data and the package-first agent-platform tables. Startup schema repair lives in `backend/app/db/`; Alembic scaffolding is not the live upgrade authority.

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
| `workflow_packages` | mutable package headers with stable key, name, description, status, draft source, and latest version pointers |
| `workflow_package_versions` | immutable package manifests, package definitions, compiled plans, hashes, validation summaries, and launch timestamps |
| `model_connections` | global saved provider/model endpoint config, encrypted API keys, health/test metadata, and archive state |
| `runs` | global persisted package execution input/output, status, totals, trace ids, rerun/replay metadata, package provenance, and no-secret launch snapshots |
| `run_steps` | persisted workflow step status, copied replay context, graph metadata, errors, and timestamps |
| `run_agent_invocations` | persisted agent invocation lineage, resolved inputs, outputs, token usage, durations, and copied replay context |

Package-private agents, output schemas, capability profiles, private MCP configs, and workflow graphs are stored inside immutable package version JSON. They are not normalized into global authoring tables.

## Integrity Rules

- Money, quantities, and market values stay decimal-safe and cross the API as strings.
- Portfolio-owned records enforce portfolio isolation through foreign keys and service lookups.
- Trading operations are append-only; full sell-down may delete the current aggregate position row.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content updates are allowed. `source` describes origin with canonical values `compiled`, `uploaded`, `external`, and `agent`; `external` is for true external user/API-created reports, not agent-created reports.
- Package versions are immutable after creation; package exports omit secrets, encrypted credential payloads, database ids, and run history.
- Model-connection secrets remain encrypted at rest and masked in reads/errors. Workflow package manifests store model connection keys as live bindings, not provider credentials.
- Global tools are read-only server-declared metadata, exposed by API and referenced by package-local capability profiles.
- Runs store package id, package key, package version, package hash, workflow key, local resource refs, resolved model connection refs, and no-secret launch snapshots.
- Startup repair handles current platform tables through `backend/app/db/upgrades.py`, including `workflow_packages`, `workflow_package_versions`, `runs`, `run_steps`, and `run_agent_invocations`.

## Retired Data

Backtest, simulation, orchestration, Studio, Tryout, runtime-v2, legacy skill-contract tables, and old global authoring tables for agents, capabilities, MCP servers, output schemas, and workflows are not part of the current shipped data contract. Do not reintroduce them as live schema documentation targets.
