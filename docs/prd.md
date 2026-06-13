# Product Requirements Document

> Status: Live product-scope reference for branch `main` at `f4f487f`.

## Product Summary

SignalDeck is a trusted single-user portfolio workspace and universal agents workflow/pipeline platform. The shipped browser surface covers the Finance Workspace, Templates, Reports, Workflow Packages, Model Connections, Extensions, Runs, and trusted local operator Memory Admin over canonical workflow memory. Tools are shipped as backend metadata at `/api/tools` and as package-authoring choices, not as a standalone browser page.

Executable agent workflows enter the system only as Workflow Packages. Preserved portfolio, template, report, market-data, and finance runtime-tool behavior is supplied by the statically resident first-party `signaldeck.finance` extension, which is enabled by default and exposed through state gates rather than marketplace installation or plugin hot-loading.

Digital Oracle runtime support ships through the statically resident bundled `signaldeck.digital_oracle` extension, label `Digital Oracle Runtime`, which is enabled by default and tool-only in this upgrade. It owns `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup`; their tool keys and OpenAI function names stay unchanged. The Digital Oracle research methodology is package-local prompt policy in an agent `systemPrompt`, not a global skill surface; the final proven demo artifact path is `demo/digital_oracle_researcher.yaml`.

## Goals

- Keep portfolio balances, positions, market context, and simulated trading operations isolated by portfolio.
- Let users author reusable text templates and compile them against live portfolio, report, and runtime-input data.
- Preserve point-in-time markdown reports that can be generated, uploaded, edited, filtered, and downloaded by slug.
- Let users author Workflow Packages without code changes, then launch saved packages from a dedicated `Launch Workflow Package` page.
- Keep Model Connections, Extensions, Runs, and Memory as global browser platform surfaces around package-owned workflows, with Tools available as server-declared metadata for package authoring and runtime grants.
- Persist package runs with inspectable inputs, package provenance, per-step outputs, operation evidence, final output, status, progress, queue state, token usage, trace metadata, memory evidence, typed tool-failure taxonomy, and bounded retry evidence.
- Keep local persistence authoritative when quote providers, model providers, tracing, or optional external data sources are unavailable.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, realtime quotes, alerts, tax-lot accounting, or user-facing autonomous scheduling products. The backend run scheduler is internal queue infrastructure only.
- Removed Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract, global Digital Oracle skill, or standalone global authoring browser/API surfaces.
- TradingAgents-specific platform behavior or exact LangGraph graph parity. TradingAgents is smoke/demo package data and research rationale only.
- Unscoped runtime memory search, public memory CRUD, exact-id runtime memory get, embeddings, or memory chunk-table workflows in the current phase.

## Product Areas

1. Finance Workspace: portfolio list/detail, balances, positions, CSV import, trades, quote-enriched metrics, finance routes, and degraded-provider warnings.
2. Template manager: global templates, placeholder browser, runtime inputs, inline compile preview, stored-template compile, and schema display metadata.
3. Reports workspace: compiled, uploaded, external, and agent-origin markdown reports with grouping, filters, edit, delete, and download.
4. Workflow Packages: YAML manifest authoring for package-local agents, agent `systemPrompt` methodology, output schemas, capability profiles, private MCP configs, workflow graphs, HTTP operation nodes, validation, import, export, and package-local secret binding management. The editor is authoring-only; launch runtime state lives outside it. The Digital Oracle researcher demo is documented as `demo/digital_oracle_researcher.yaml`, with promotion handled by the demo artifact task.
5. Model Connections: global saved OpenAI-family endpoint/model bindings, `protocolProfile` selection, backend-owned compatibility evidence, capability probes, reachability tests, encrypted secrets, and secret-safe reads. Public writes no longer author capability, policy, probe-cache, or derived API-style truth.
6. Extensions: slim enable/disable state for statically resident extensions. Public state is only `key`, `label`, and `enabled`.
7. Tools metadata: global read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles. Finance-owned entries cover market data, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup. Digital Oracle-owned entries cover `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup`; platform-core entries cover memory write/lookup. Retired report-write tooling is fail-closed, not a live tool. There is no standalone `/tools` browser route.
8. Runs: global run list/detail, dedicated package launch, backend-owned progress and queue state, run-owned package snapshots, operation invocation evidence, memory evidence, root-parameter reruns, invocation-input forks, historical replay lineage reads, typed tool-failure taxonomy, and bounded model-feedback retry evidence.
9. Memory: platform-core scoped runtime `/api/memory` workflows plus trusted local operator `/api/memory/admin/entries*` and `/memory` admin management over canonical workflow memory across packages. Runtime `signaldeck.memory.lookup/write` and scoped `/api/memory` remain package/run/agent/scope-bound and do not expose finance report history as memory.

## Success Criteria

- A user can create a portfolio, add balances and positions, and submit valid simulated operations without crossing portfolio boundaries.
- Template compile and report generation work with `inputs`, `portfolios`, and `reports` placeholders.
- Runtime input schema `title` and `description` fields improve generated launch-form labels/help text without changing runtime semantics.
- Report-series workflows can reuse stable tags and runtime inputs to reference the latest prior report in a series.
- Report list/detail/download flows remain slug-addressed and source-aware across `compiled`, `uploaded`, `external`, and `agent` origins.
- Historical agent-memory reports remain report-domain records, while canonical memory writes, lookup, scoped `/api/memory`, and trusted `/memory` admin use platform-core memory tools, tables, scopes, status, provenance, and runtime grant checks.
- Workflow Packages can be authored from `signaldeck.workflowPackage/v1` YAML manifests, validated before save, and exported/imported without database ids, run history, package secret binding rows, or raw secret values.
- The Workflow Package editor stays authoring-only and does not own launch runtime state.
- Package launches start from `/workflow-packages/:packageId/run`, create durable queued runs, and expose package provenance, progress, queue explanations, per-step agent/operation details, final output, memory evidence, typed failures, retry evidence, and safe error states.
- Reruns edit root launch parameters; forks edit a selected agent invocation input and resume from the persisted execution boundary.
- Model Connections remain global live bindings with backend-owned compatibility truth, global Tools remain read-only metadata, Digital Oracle phase-1 tools remain package-authoring choices behind `signaldeck.digital_oracle`, platform-core memory tools and admin/runtime memory surfaces remain separate from finance, and package-private resources stay inside package versions.
- The Digital Oracle researcher package documents its methodology in package-local `systemPrompt` text and uses `demo/digital_oracle_researcher.yaml` as the final proven artifact path, without adding a global skill or phase-2 tool claim.
