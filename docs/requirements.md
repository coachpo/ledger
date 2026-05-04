# Requirements Document

> Status: Live requirements reference as of 2026-05-04 (`b4ac445`).

## Purpose

Define the shipped Ledger requirements for a trusted single-user portfolio workspace and stateless agent platform. Live code is the source of truth; this document mirrors the browser and API surfaces mounted at the current branch tip.

## Product Scope

### In Scope

- Portfolio CRUD with balances, positions, CSV import, quote/history context, and trading operations.
- Template CRUD, placeholder browsing, inline compile, stored-template compile, and runtime inputs.
- Report generation from templates, external JSON report creation, markdown upload, slug CRUD, filtering, and download.
- Agent CRUD and YAML manifest validation.
- Capability CRUD with canonical `toolGrants` and server-declared tool catalog integration.
- MCP server CRUD, security validation, connection testing, exact-pinned versions, and runtime tool snapshots.
- Model connection CRUD, encrypted stored secrets, OpenAI-family URL normalization, and connection testing.
- Output schema CRUD, schema composer, locked JSON Schema subset validation, preview, and runtime compilation.
- Workflow CRUD, YAML manifest validation, launch metadata, version reads, launches, and run creation.
- Run list/detail, rerun drafts, reruns, step replay drafts, and step replays.
### Out Of Scope

- Public multi-user auth, live broker execution, realtime market streaming, and tax-lot accounting.
- Retired `/api/skills`, `/skills*`, Studio, Tryout, orchestration, runtime-v2, simulations, and backtest workflows.
- Raw HTTP LLM calls in application code when an official provider SDK exists.

## Functional Requirements

### FR-1 Portfolios, Balances, Positions, And Trades

- The system must isolate portfolio-owned balances, positions, trading operations, quote lookups, and analytics by `portfolioId`.
- Position CSV import must use preview and commit endpoints with row-level errors and atomic upsert-by-symbol commit.
- Trading operations must support BUY, SELL, DIVIDEND, and SPLIT with deterministic cash/position updates.
- Quote/history failures must degrade to warnings rather than making local portfolio records unusable.

### FR-2 Templates And Reports

- Templates must support `inputs`, `portfolios`, and `reports` placeholder roots.
- Dynamic portfolio and report selectors must accept runtime inputs where supported.
- Reports must support canonical `source` origins `compiled`, `uploaded`, `external`, and `agent`.
- `external` must remain limited to true external user/API-created reports; agent-created reports must use `source="agent"`.
- Report reads, updates, deletes, and downloads must be slug-addressed.
- Report metadata must remain extensible JSON while canonical filters stay stable. For agent memory reports, `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"` describe purpose/type, while server-owned `metadata.createdBy.type="agent"` records provenance including `runId`, `agentKey`, and `agentVersion`.

### FR-3 Agent Platform Authoring

- Agents and workflows must be YAML-manifest based and reject aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate refs, non-exact version pins, and retired `spec.skills` fields.
- Capabilities must be the canonical tool-grant resource and expose API payloads with `toolGrants`.
- MCP server saves/tests must enforce URL, stdio, exact-pin, snapshot, and redaction rules.
- Model connections must preserve or replace stored secrets safely and never return raw secrets in read payloads.
- Output schemas must validate against the supported schema subset before save and before runtime use.
- Workflow launches must use the strict `{version, parameters}` envelope and create queued runs.
- Runs must expose input, per-step outputs, final output, status, timing, cost, trace ids, rerun metadata, and step replay metadata.

## Non-Functional Requirements

- Backend stack: Python 3.13+, FastAPI, SQLAlchemy, Pydantic, PostgreSQL.
- Frontend stack: React 19, Vite, TanStack Query, React Router, shadcn/ui, Vitest, Playwright.
- Backend validation errors must use the shared error envelope.
- Application LLM calls must use official SDKs rather than raw provider HTTP paths.
- CI must run version sync, backend quality, frontend quality, and frontend E2E.

## Acceptance Criteria

- A user can manage portfolio records and reports without provider availability.
- A user can configure model connections, capabilities, agents, output schemas, workflows, and inspect runs from the browser.
- Retired Studio, Tryout, orchestration, runtime-v2, simulation, backtest, `/api/skills`, and `/skills*` routes are not presented as current product surfaces.
