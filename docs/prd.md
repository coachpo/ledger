# Product Requirements Document

> Status: Live product-scope reference as of 2026-05-04 (`b4ac445`).

## Product Summary

Ledger is a trusted single-user portfolio workspace with preserved portfolio, template, and report workflows plus the current YAML-authored agent-platform surfaces. The shipped browser surface covers portfolios, templates, reports, agents, capabilities, MCP servers, model connections, output schemas, workflows, and runs.

## Goals

- Keep portfolio balances, positions, market context, and simulated trading operations isolated and editable.
- Let users author reusable text templates and compile them against live portfolio, report, and runtime-input data.
- Preserve point-in-time markdown reports that can be generated, uploaded, edited, filtered, and downloaded by slug.
- Let users configure agents, capabilities, MCP servers, model connections, output schemas, and workflows without code changes.
- Persist workflow runs with inspectable inputs, per-step outputs, final output, status, timing, cost, and trace-linkage metadata.
- Keep local persistence authoritative when quote providers, model providers, or tracing systems are unavailable.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, realtime quotes, alerts, or autonomous schedulers.
- Retired Studio, Tryout, orchestration, runtime-v2, simulations, backtests, or skill-contract browser/API surfaces.
- Raw HTTP LLM provider integrations when an official SDK exists.

## Product Areas

1. Portfolio workspace: portfolio list/detail, balances, positions, CSV import, trades, quote-enriched metrics, and warnings.
2. Template manager: global templates, placeholder browser, runtime inputs, inline compile preview, and stored-template compile.
3. Reports workspace: generated, uploaded, and external markdown reports with grouping, filters, edit, delete, and download.
4. Agent authoring: YAML manifest list/editor/run-launch flows for versioned agents.
5. Capabilities: canonical tool-grant CRUD with `toolGrants` and server-declared tools.
6. MCP servers: saved server config, security validation, connection testing, and runtime snapshots.
7. Model connections: saved OpenAI-family endpoints, encrypted secrets, connection tests, and secret-safe read payloads.
8. Output schemas: schema composer, JSON preview, validation, versioning, and runtime compilation.
9. Workflows and runs: YAML workflow editor, launches, run monitor, reruns, and step replays.

## Success Criteria

- A user can create a portfolio, add balances and positions, and submit valid simulated operations without crossing portfolio boundaries.
- Template compile and report generation work with `inputs`, `portfolios`, and `reports` placeholders.
- Report-series workflows can reuse stable tags and runtime inputs to reference the latest prior report in a series.
- Report list/detail/download flows remain slug-addressed and source-aware.
- Agents and workflows can be authored from YAML manifests and validated before save.
- Capability, MCP server, model connection, and output schema resources can be created and reused by agents/workflows.
- Workflow launches create persisted runs with visible per-step details, final output, and safe error states.
