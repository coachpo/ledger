# TradingAgents-Informed SignalDeck Upgrade Design

> Status: Research and design note for branch `main` at `596ee84`. Merges the TradingAgents/SignalDeck workflow comparison with the forward-looking upgrade design; live code remains the source of truth.

## Intent

SignalDeck should absorb useful TradingAgents capability patterns without adopting the TradingAgents runtime model. SignalDeck can approximate TradingAgents best as an auditable advisory/research Workflow Package, not as an exact LangGraph clone.

TradingAgents-style research is one package template and use case. Workflow Package semantics must stay universal and unchanged, and exact LangGraph graph parity is permanently rejected.

The application has no users yet, so prefer clean contracts over compatibility shims. Existing `kind: step` semantics remain unchanged: a step uses a local package agent.

TradingAgents source review used DeepWiki plus GitHub source evidence from TradingAgents HEAD `a5cb7cbd61d217fb0bc43f017392a861257afe6a`, then checked current public README/changelog terminology through v0.2.5 from 2026-05-11.

## Settled Scope

In scope:

- Native SignalDeck data/news and social sentiment runtime tools, migrated or refactored from useful TradingAgents collectors where appropriate.
- Report-backed memory follow-up automation for pending decisions, delayed outcome resolution, reflection text, and future prompt snippets.
- A canonical TradingAgents-style Workflow Package template for advisory research.
- Advisory-only final decisions. The package outputs a proposed decision and advice, not trade execution.
- A new non-agent HTTP workflow node for webhooks, notifications, callbacks, and deterministic API handoffs.

Out of scope:

- LangGraph-compatible node/edge/checkpoint runtime semantics.
- MCP-backed built-in data collection. MCP stays a user customization surface for Workflow Packages.
- Agent-initiated trading execution or automatic trade-operation drafts.
- Public memory APIs, memory tables, vector search, or embeddings in this upgrade.

## Remaining Comparison

| Area | TradingAgents | TradingAgents implementation | SignalDeck equivalent | Match | Winner |
|---|---|---|---|---|---|
| Runtime execution | LangGraph node execution with checkpoint resume | `TradingAgentsGraph` compiles a LangGraph `StateGraph`, can use per-ticker SQLite checkpointing, runs with a ticker/date `thread_id`, and clears checkpoints after success. | Persisted Runs with steps, invocations, rerun, and step replay; recovery semantics are similar but not identical. | Medium-High | SignalDeck, for durable audit/replay design; TradingAgents remains stronger for native graph checkpoint semantics. |
| Memory | Markdown decision log with automatic return/reflection updates and future prompt context | `TradingMemoryLog.store_decision()` appends pending markdown decisions; later runs resolve pending entries with raw/alpha returns, call `Reflector`, and inject past context into the Portfolio Manager prompt. | Report-backed memory via `signaldeck.reports.lookup` and `signaldeck.reports.write`; memory is durable, but return/reflection flow is a different report-backed model. | Medium | TradingAgents, for purpose-built trading reflection; SignalDeck has stronger persistence but less automatic feedback-loop design. |
| Analyst phase | Analyst team feeds staged debates and decisions | Source and public docs describe selected analysts, tool loops, bull/bear debate, research manager, trader, risk debate, and portfolio manager handoff. | The existing fixture uses analyst `fanout`; SignalDeck can model fanout, sequence, or staged handoff explicitly when authored that way. | Medium | Tie; TradingAgents has source-native analyst/debate orchestration, while SignalDeck can implement the same practical topology through manifest structure. |
| External data/news research | Source-specific vendor data and news tools with query/fallback behavior, not a generic browser-search runtime | News and data tools route through vendor selection such as `route_to_vendor`; news analysts call `get_news` and `get_global_news` tools for company and macro context. | Private MCP such as Exa MCP in the fixture plus native news/fundamentals/insider tools; coverage depends on configured tools and MCP availability. | Medium | TradingAgents, for built-in market research integrations; SignalDeck depends on configured MCP/tool availability. |
| **REJECTED - NEVER IMPLEMENT: True graph parity** | LangGraph conditional graph with node-level control flow | TradingAgents is genuinely graph-driven: compiled `StateGraph`, conditional edges, tool loops, debate loops, and portfolio-manager termination. Exact parity means matching LangGraph runtime behavior. | SignalDeck compiles manifest graph to planned steps; graph metadata is preserved, but execution is intentionally not a LangGraph-equivalent graph runtime. | Rejected | TradingAgents wins exact graph parity, but SignalDeck must never chase this target because it would change Workflow Package semantics. |
| Trading execution | Trading decision and simulated-exchange framing | `Trader` produces a proposal, risk debate reviews it, and `PortfolioManager` approves or rejects the action in a simulated-exchange framing; this is not live broker execution. | SignalDeck package output is advisory; actual trading operations remain separate portfolio/trading APIs. | Medium | TradingAgents, for integrated trading-decision framing; SignalDeck intentionally separates advisory runs from trade APIs. |
| Sentiment Analyst / social feeds | Current TradingAgents sentiment path can use Yahoo News, StockTwits, and Reddit | The grounded Sentiment Analyst prefetches Yahoo news, StockTwits, and Reddit before the LLM call; source fetchers return prompt-safe source blocks and degrade gracefully. | Current committed SignalDeck has no native social sentiment lookup; it requires a new native tool, MCP, or omission until implemented. | Low-Medium | TradingAgents, because those sentiment sources are closer to the original implementation path. |

Filtered-out rows include workflow container, agent roles, debate loops, shared state handoff, structured outputs, market/tool categories, auditability, and model configuration because SignalDeck can reach the same practical runnable outcome through its package, schema, tool, run, and model-connection surfaces.

Approximate remaining-gap fit after rejecting exact graph parity: 8/10 conceptual research-workflow match, 5/10 exact runtime/topology match, and 9/10 auditability match.

## Implementation Feasibility

SignalDeck should absorb the useful capability patterns, not the TradingAgents runtime model. The safe path is to add universal tools, services, and templates that benefit more than this one use case.

| Row | TradingAgents approach to migrate or mimic | Feasibility | SignalDeck implementation sketch | SignalDeck-safe analysis |
|---|---|---|---|---|
| Runtime execution | Mimic durable recovery goals, not LangGraph checkpoint internals. | Partial | Improve Runs around existing provenance, rerun, and step replay views; do not add per-node LangGraph checkpoints. | Keep SignalDeck Runs, rerun, and step replay as the universal mechanism. Do not import per-node LangGraph checkpoint semantics. |
| Memory | Mimic pending decision, delayed outcome resolution, reflection generation, and future prompt context. | High | Add an additive memory follow-up flow that resolves pending memories after horizon, appends reflections, and feeds prompt snippets through `MemoryContextService`. | Feasible through existing `MemoryService`, `ReturnResolutionService`, `ReflectionService`, and `MemoryContextService`, while staying report-backed and keeping stable `signaldeck.reports.*` tool names. |
| Analyst phase | Mimic the staged analyst/debate topology through authored workflow order. | Already feasible | Ship a canonical Workflow Package template that uses `sequence`, `fanout`, `loop`, and structured outputs for analyst/debate stages. | Use `sequence`, `fanout`, `loop`, structured outputs, and package templates. No platform function or runtime semantic change is required. |
| External data/news research | Mimic vendor-routed source-specific data and news retrieval. | High | Migrate and refactor the useful TradingAgents data/news collection functions into native SignalDeck runtime tools, then expose them through capability profiles. | Implement as SignalDeck tools, never MCPs. MCP remains only a user customization surface for workflow packages. |
| Sentiment Analyst / social feeds | Mimic the prefetch-and-summarize sentiment approach. | Medium-High | Migrate and refactor useful Yahoo News, StockTwits, and Reddit-style collectors into native SignalDeck sentiment tools that return normalized source blocks and source metrics for agents to summarize. | Provider access, rate limits, and source reliability are the main constraints. Implement as generic SignalDeck tools, never TradingAgents-specific MCP presets. |
| Trading execution | Mimic proposal-to-review-to-decision flow, not live execution. | Not needed | Output only the proposed decision and advice from the workflow package. | This application does not need trading execution; keep the result advisory-only and do not create trade-operation drafts from runs. |
| **REJECTED - NEVER IMPLEMENT: True graph parity** | Do not migrate or mimic exact compiled LangGraph runtime semantics. | Rejected | Implement nothing for exact parity; document it as a non-goal and use only current package graph metadata, rerun, and step replay. | Exact node/edge/checkpoint parity would turn Workflow Packages into a LangGraph clone and violate SignalDeck's universal workflow-platform design. Only approximate outcomes with current package semantics. |

Best implementation targets are memory/reflection automation, native SignalDeck data/news and social sentiment tools, and a canonical TradingAgents-style package template. The permanently rejected target is exact graph parity; trading execution stays advisory-only.

## Upgrade Tracks

### Native Data And Social Tools

TradingAgents already contains practical data collection functions for vendor-routed news and prefetch-style social sentiment. SignalDeck should migrate the useful ideas into native runtime tools, not MCP presets.

Design:

- Keep native tool metadata under `/api/tools` and package grants under capability profiles.
- Preserve stable existing tool keys such as `signaldeck.news.lookup`; add new keys only for new contracts such as normalized social sentiment lookup.
- Normalize provider output into bounded JSON plus prompt-safe source blocks.
- Return structured warnings on provider outage, rate limit, empty result, or partial coverage.
- Keep provider adapters behind backend services, not inside route handlers or workflow manifests.

Suggested tool families:

- Extend `signaldeck.news.lookup` for source-specific company and macro news retrieval.
- Add `signaldeck.social_sentiment.lookup` for Reddit/StockTwits-like source blocks and metrics.
- Keep `signaldeck.fundamentals.lookup` and `signaldeck.insider_data.lookup` as financial context tools.

### Memory Follow-Up Automation

SignalDeck already has `MemoryService`, `ReturnResolutionService`, `ReflectionService`, and `MemoryContextService`. The upgrade should connect them with explicit post-run automation, not hidden workflow loops.

Design:

- Memory writes stay report-backed through `signaldeck.reports.write`.
- A follow-up service finds pending memory entries whose horizon has matured.
- Return resolution computes raw return, benchmark return, and alpha through existing market-data services.
- Reflection text is appended through `ReflectionService`.
- Future runs use `MemoryContextService` prompt snippets, never raw report markdown.
- Idempotency keys prevent duplicate resolution/reflection work.

### Canonical Advisory Package Template

Ship a canonical package manifest that demonstrates the TradingAgents-style advisory workflow using existing universal semantics.

Template shape:

- Analyst stage with either `fanout` or explicit `sequence`, depending on the intended research behavior.
- Debate loops using existing `loop` nodes and structured transition schemas.
- Final advisory decision output with posture, rationale, risk summary, and implementation notes.
- Native data/news/social tools granted through capability profiles.
- Memory lookup/write tools granted only to agents that need historical context or final memory writes.
- No trade execution. The final output is advice only.

## Non-Agent HTTP Nodes

HTTP callbacks are useful for notifications and deterministic handoffs, but they are not agents. Add a dedicated workflow node kind instead of overloading `kind: step`, because today `step.uses` means local agent.

Use `kind: http` as the public manifest contract. Reserve a broader internal `ExecutionPlanOperation` abstraction for future non-agent families if SignalDeck later adds `delay`, `approval`, `transform`, or other operation kinds.

### Manifest Sketch

Keep current agent step unchanged. Add a new workflow node kind:

```yaml
- kind: http
  id: notify_slack
  slot: notification_result
  method: POST
  url: ${{ inputs.webhookUrl }}
  headers:
    Content-Type: application/json
    Authorization: ${{ secrets.slackWebhookToken }}
  body:
    ticker: ${{ inputs.ticker }}
    decision: ${{ nodes.portfolio_manager_review.outputs.decision.posture }}
  response:
    outputSchema: webhook_response
  timeoutSeconds: 10
  optional: false
```

Use a dedicated `kind: http` instead of overloading existing `kind: step`, because today `step.uses` means local agent. That keeps existing Workflow Package behavior intact.

### Backend Shape

Add:

- `WorkflowPackageHttpNode` to `workflow_package_manifest.py`.
- Compiler support in `workflow_package_manifest_compiler.py`.
- Execution-plan support for non-agent step slots, probably `ExecutionPlanOperation`.
- A run execution branch in `RunService._execute_step()`:
  - agent slots continue through `AgentExecutionService`;
  - HTTP operation slots go through a new `HttpOperationExecutionService`.
- Persistence either:
  - add `run_operation_invocations`, cleaner long-term;
  - or generalize `run_agent_invocations` later, but do not overload it now because it has required agent/schema fields.

Preferred shape:

- Add `PackageRuntimeOperationSpec` and `ExecutionPlanOperation` beside `PackageRuntimeAgentSpec` and `ExecutionPlanAgent`.
- Extend `ExecutionPlanStep` to hold both `agents` and `operations`.
- Keep final outputs as step/slot selectors so downstream references work for both agents and operations.

### HTTP Runtime Contract

The HTTP service should:

- resolve inputs from workflow inputs and prior node outputs;
- build method, URL, headers, query, and body;
- execute only GET and POST initially, with PUT, PATCH, and DELETE behind explicit server configuration if ever needed;
- enforce timeout, maximum request body size, maximum response body size, and bounded redirect policy;
- capture status code, selected response headers, parsed JSON or text body, duration, and structured errors;
- validate output against `response.outputSchema`;
- persist resolved request metadata and response metadata for audit.

Secrets should be referenced, not embedded. For the first version, use existing package/private config style or a small package secrets binding model, but do not expose secret values in run details.

### Persistence Model

Create `run_operation_invocations` rather than forcing operations into `run_agent_invocations`.

Recommended fields:

- `run_step_id`, `run_id`, `step_index`, `slot`, `position`, `operation_kind`, `operation_key`.
- `status`, `optional`, `wiring`, `graph_metadata`, `resolved_input`, `resolved_input_origin`.
- `resolved_request` with redacted URL, method, headers, query metadata, body digest, and body preview.
- `response` with status code, selected headers, parsed body, raw text preview, and truncation flags.
- `output`, `output_origin`, `error_code`, `error_message`, `error_details`.
- `duration_ms`, `started_at`, `finished_at`, `persisted_at`, and copied-source fields for step replay.

Run detail should expose operation invocations separately from agent invocations. The frontend can render them in the same step timeline with an explicit `operation` badge.

### Security Rules

HTTP nodes are an SSRF and secret-exfiltration boundary. The first version should be strict:

- Block localhost, loopback, link-local, private network, metadata-service, and unix-socket targets by default.
- Allow only HTTPS unless an explicit development setting permits HTTP.
- Resolve DNS and validate the final address before connecting.
- Redact secret-backed headers and body fields from run detail.
- Persist secret references and redacted metadata, never secret values.
- Limit redirects and re-check every redirect target.
- Enforce per-call timeout, response limits, and allowed content types.
- Treat non-2xx responses as failures unless the node declares accepted status codes in a later version.

## Implementation Phases

1. Native data/news/social tools.
   - Migrate/refactor useful collector logic into backend services.
   - Register new or expanded runtime tool specs.
   - Add provider warnings and deterministic fixture coverage.
2. Memory follow-up automation.
   - Add an idempotent service that resolves matured memory and appends reflections.
   - Keep memory report-backed and prompt-safe.
3. Canonical advisory package template.
   - Publish a clean package manifest that uses native tools and advisory-only output.
4. HTTP node foundation.
   - Add manifest schema, compiler, execution-plan, persistence, runtime service, and run detail support.

## Validation Plan

Backend tests:

- Manifest parser/compiler tests for `kind: http`, secret refs, output schema refs, optional nodes, invalid methods, invalid URLs, and duplicate slots.
- Execution-plan tests proving mixed agent and HTTP operation steps resolve inputs and prior outputs.
- Run-service tests for successful HTTP execution, optional failure, fatal failure, response validation failure, replay copying, and final output selection from operation slots.
- Security tests for private IPs, localhost, redirects, body limits, response limits, and secret redaction.
- Runtime-tool tests for native data/news/social tools and warning behavior.
- Memory tests for follow-up idempotency, return resolution, reflection append, and prompt snippet rendering.

Frontend tests:

- Workflow package editor/preflight tests for HTTP node validation messages.
- Run detail tests for operation invocation rows, redacted request metadata, response preview, and failure display.

Manual QA:

- Launch an advisory package that writes memory and returns a proposed decision.
- Resolve a matured memory and confirm reflection appears in future prompt context.
- Launch a package with a safe local test webhook and confirm operation audit metadata is redacted and visible in run detail.

## Feasibility

This is feasible and aligned with SignalDeck if implemented as additive platform capability:

- Native research/social tools are straightforward extensions of the existing runtime tool catalog.
- Memory follow-up automation builds on existing memory services and keeps report-backed persistence.
- The advisory template is already close to the current TradingAgents fixture and does not require runtime changes.
- HTTP nodes are medium-large because manifest, compiler, execution plan, run execution, persistence, and run detail are currently agent-invocation-shaped.

The clean design is still worth it. HTTP operations give workflows normal non-agent actions such as webhooks, notifications, HTTP callbacks, and deterministic API handoffs without turning SignalDeck into a general code runner or a LangGraph clone.

## Design Decision Summary

- Implement data/news/social collection as native SignalDeck tools, never MCPs.
- Keep trading output advisory-only.
- Use `kind: http` for the first non-agent operation node.
- Add dedicated operation execution and persistence instead of overloading agents.
- Keep secrets referenced and redacted.
- Keep exact graph parity rejected permanently.
