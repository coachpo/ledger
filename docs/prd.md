# Product Requirements Document

> Status: Live product-scope reference for the current branch.

## Product Summary

SignalDeck is a trusted single-user workflow/report workspace and universal agents workflow/pipeline platform. The shipped browser surface covers the Finance Workspace, Templates, Reports, Workflow Packages, Model Connections, and Runs. Tools are shipped as backend metadata at `/api/tools` and as package-authoring choices, not as a standalone browser page.

Executable agent workflows enter the system only as Workflow Packages. Preserved template, report, market-data provider, and finance runtime-tool behavior is supplied by the statically resident first-party `signaldeck.finance` extension, which is installed by code rather than marketplace installation, plugin hot-loading, or runtime state gates.

Digital Oracle runtime support ships through the statically resident bundled `signaldeck.digital_oracle` extension, which is tool-only in this upgrade. It owns `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`; their tool keys are canonical owner-qualified contracts and their OpenAI function names are mechanical forms derived from those keys. The Digital Oracle research methodology is package-local prompt policy in an agent `systemPrompt`, not a global skill surface; the final proven demo artifact path is `demo/digital_oracle_researcher.yaml`.

## Goals

- Let users author reusable text templates and compile them against live report and runtime-input data.
- Keep finance provider tools available for package-owned research workflows with degraded-provider warnings.
- Preserve point-in-time markdown reports that can be generated, uploaded, edited, filtered, and downloaded by slug.
- Let users author Workflow Packages without code changes, then launch saved packages from a dedicated `Launch Workflow Package` page.
- Keep Model Connections and Runs around package-owned workflows, with Tools available as server-declared metadata for package authoring and runtime grants.
- Persist package runs with inspectable inputs, package provenance, per-step outputs, operation evidence, final output, status, progress, queue state, token usage, trace metadata, typed tool-failure taxonomy, and bounded retry evidence.
- Keep local persistence authoritative when quote providers, model providers, tracing, or optional external data sources are unavailable.

## Non-Goals

- Authentication, authorization, or multi-tenant account management.
- Live broker integration, order routing, realtime quotes, alerts, tax-lot accounting, or user-facing autonomous scheduling products. The backend run scheduler is internal queue infrastructure only.
- Removed Studio, Tryout, orchestration, runtime-v2, simulations, backtests, skill-contract, global Digital Oracle skill, or standalone global authoring browser/API surfaces.
- TradingAgents-specific platform behavior or exact LangGraph graph parity. TradingAgents is smoke/demo package data and research rationale only.
- Workflow-memory governance, `spec.memory`, `/api/memory`, runtime memory tool calls, memory review UI, checkpoints, vector retrieval, or `workflowMemoryEvidence`.

## Product Areas

1. Finance Workspace: template/report routes, finance provider services, finance runtime tools, and degraded-provider warnings.
2. Template manager: global templates, placeholder browser, runtime inputs, inline compile preview, stored-template compile, and schema display metadata.
3. Reports workspace: compiled, uploaded, external, and agent-origin markdown reports with grouping, filters, edit, delete, and download.
4. Workflow Packages: YAML manifest authoring for package-local agents, agent `systemPrompt` methodology, output schemas, capability profiles, private MCP configs, workflow graphs, HTTP operation nodes, validation, import, export, and package-local secret binding management. The editor is authoring-only; launch runtime state lives outside it. The Digital Oracle researcher demo is documented as `demo/digital_oracle_researcher.yaml`, with promotion handled by the demo artifact task.
5. Model Connections: global saved OpenAI-family endpoint/model bindings, `protocolProfile` selection, backend-owned capability evidence, capability probes, reachability tests, encrypted secrets, and secret-safe reads. Public writes no longer author capability, policy, probe-cache, or derived API-style truth.
6. Tools metadata: global read-only server-declared metadata exposed through `/api/tools` and referenced by package-local capability profiles. Finance-owned entries cover market data, indicators, fundamentals, news, social sentiment, insider data, and report lookup. Digital Oracle-owned entries cover `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`. There is no standalone `/tools` browser route and no server-declared memory tool surface.
7. Runs: global run list/detail, dedicated package launch, backend-owned progress and queue state, run-owned package snapshots, operation invocation evidence, root-parameter reruns, typed tool-failure taxonomy, and bounded model-feedback retry evidence.

## Success Criteria

- Template compile and report generation work with `inputs` and `reports` placeholders.
- Runtime input schema `title` and `description` fields improve generated launch-form labels/help text without changing runtime semantics.
- Report-series workflows can reuse stable tags and runtime inputs to reference the latest prior report in a series.
- Report list/detail/download flows remain slug-addressed and source-aware across `compiled`, `uploaded`, `external`, and `agent` origins.
- Agent-origin reports remain report-domain records and are not promoted into a separate workflow-memory substrate.
- Workflow Packages can be authored from `signaldeck.workflowPackage/v1` YAML manifests, validated before save, and exported/imported without database ids, run history, package secret binding rows, or raw secret values.
- The Workflow Package editor stays authoring-only and does not own launch runtime state.
- Package launches start from `/workflow-packages/:packageId/run`, create durable queued runs, and expose package provenance, progress, queue explanations, per-step agent/operation details, final output, typed failures, retry evidence, and safe error states.
- Reruns edit root launch parameters.
- Model Connections remain global live bindings with backend-owned capability and runtime-profile truth, global Tools remain read-only metadata, Digital Oracle native tools remain package-authoring choices behind `signaldeck.digital_oracle`, and package-private resources stay inside package versions.
- The Digital Oracle researcher package documents its methodology in package-local `systemPrompt` text and uses `demo/digital_oracle_researcher.yaml` as the final proven artifact path, without adding a global skill, generic web-search global tool, route, or nav claim.
