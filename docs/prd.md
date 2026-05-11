# Product Requirements Document

> Status: Live product-scope reference for branch `main` at `10063aa`.

## Product Summary

Ledger is a trusted single-user portfolio workspace with preserved portfolio, template, and report workflows plus the package-first agent-platform surface. The shipped browser surface covers portfolios, templates, reports, Workflow Packages, Model Connections, and Runs.

## Goals

- Keep portfolio balances, positions, market context, and simulated trading operations isolated and editable.
- Let users author reusable text templates and compile them against live portfolio, report, and runtime-input data.
- Preserve point-in-time markdown reports that can be generated, uploaded, edited, filtered, and downloaded by slug.
- Let users author Workflow Packages without code changes while keeping Model Connections, Tools, and Runs global.
- Persist package runs with inspectable inputs, package provenance, per-step outputs, final output, status, timing, token usage, and trace-linkage metadata.
- Keep local persistence authoritative when quote providers, model providers, or tracing systems are unavailable.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, realtime quotes, alerts, or autonomous schedulers.
- Retired Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract, or retired legacy global authoring browser/API surfaces.
- TradingAgents-specific platform behavior. TradingAgents is smoke/demo package data only.

## Product Areas

1. Portfolio workspace: portfolio list/detail, balances, positions, CSV import, trades, quote-enriched metrics, and warnings.
2. Template manager: global templates, placeholder browser, runtime inputs, inline compile preview, and stored-template compile.
3. Reports workspace: compiled, uploaded, external, and agent-origin markdown reports with grouping, filters, edit, delete, and download.
4. Workflow Packages: YAML package manifest authoring, package-local agents, output schemas, capability profiles, private MCP configs, workflow graphs, validation, preflight, import, export, and launch flows.
5. Model Connections: global saved OpenAI-family endpoints, encrypted secrets, connection tests, and secret-safe read payloads.
6. Tools: global read-only server-declared tool metadata exposed through `/api/tools` and referenced by package-local capability profiles, covering market data, indicators, fundamentals, news, insider data, positions, reports, and report memory writes.
7. Runs: global run list/detail, package provenance, launch snapshots, reruns, and step replays.

## Success Criteria

- A user can create a portfolio, add balances and positions, and submit valid simulated operations without crossing portfolio boundaries.
- Template compile and report generation work with `inputs`, `portfolios`, and `reports` placeholders.
- Report-series workflows can reuse stable tags and runtime inputs to reference the latest prior report in a series.
- Report list/detail/download flows remain slug-addressed and source-aware across `compiled`, `uploaded`, `external`, and `agent` origins.
- Agent memory reports keep `source="agent"` for origin, `metadata.analysis.reviewType="agent_memory"` and `metadata.analysis.versionGroup="agent_memory/v1"` for purpose/type, and server-owned `metadata.createdBy.type="agent"` provenance.
- Workflow Packages can be authored from `ledger.workflowPackage/v1` YAML manifests and validated before save.
- Package exports omit secrets, encrypted values, database ids, and run history.
- Model Connections remain global live bindings, global Tools remain read-only metadata, and package-private resources stay inside package versions.
- Package launches create persisted runs with visible package provenance, per-step details, final output, and safe error states.
