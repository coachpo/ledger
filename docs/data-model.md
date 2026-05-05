# Data Model Design

> Status: Live data-model reference as of 2026-05-05 (`a8ad8fb`).

## Overview

Ledger uses PostgreSQL for preserved portfolio/report/template data and the current agent-platform tables. Startup schema repair lives in `backend/app/db/`; Alembic scaffolding is not the live upgrade authority.

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
| `agents` | YAML-authored agent manifests with immutable versions and capability refs |
| `capabilities` | canonical tool-key resources backed by server-declared tool catalog entries |
| `mcp_servers` | saved MCP server config, security metadata, connection-test results, and immutable versions |
| `model_connections` | saved provider/model endpoint config, encrypted API keys, health/test metadata, archive state |
| `output_schemas` | saved output-schema versions and schema subset metadata |
| `workflows` | YAML-authored workflow manifests, immutable versions, inputs, steps, and output refs |
| `runs` | persisted workflow execution input/output, status, totals, trace ids, rerun/replay metadata |
| `run_steps` | persisted workflow step status, copied replay context, graph metadata, errors, and timestamps |
| `run_agent_invocations` | persisted agent invocation lineage, resolved inputs, outputs, token usage, durations, and copied replay context |

## Integrity Rules

- Money, quantities, and market values stay decimal-safe and cross the API as strings.
- Portfolio-owned records enforce portfolio isolation through foreign keys and service lookups.
- Trading operations are append-only; full sell-down may delete the current aggregate position row.
- Reports keep immutable `name`, `slug`, `source`, and metadata after creation; only content updates are allowed. `source` describes origin with canonical values `compiled`, `uploaded`, `external`, and `agent`; `external` is for true external user/API-created reports, not agent-created reports. Agent memory reports keep purpose/type in `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"`, while server-owned `metadata.createdBy.type="agent"` carries provenance fields such as `runId`, `agentKey`, and `agentVersion`.
- Capabilities are the canonical tool-key table; legacy skill contracts are not a live schema target.
- Model-connection secrets must remain encrypted at rest and masked in reads/errors.
- MCP runtime execution uses exact pinned versions and frozen tool snapshots.
- Startup repair handles current platform tables through `backend/app/db/upgrades.py`, including `run_steps` and `run_agent_invocations`.

## Retired Data

Backtest, simulation, orchestration, Studio, Tryout, runtime-v2, and legacy skill-contract tables are not part of the current shipped data contract. Do not reintroduce them as live schema documentation targets.
