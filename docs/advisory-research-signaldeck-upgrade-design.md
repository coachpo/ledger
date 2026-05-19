# TradingAgents-Informed SignalDeck Upgrade Design

> Status: Research and design note for branch `main` at `69e809e`. Keeps TradingAgents/SignalDeck comparison and settled design rationale; live code and the owner docs remain the source of truth.

## Intent

SignalDeck absorbed useful TradingAgents capability patterns without adopting the TradingAgents runtime model. SignalDeck approximates TradingAgents best as an auditable advisory/research Workflow Package, not as an exact LangGraph clone.

TradingAgents-style research is one package template and use case. Workflow Package semantics stay universal, and exact LangGraph graph parity remains permanently rejected.

The application has no users yet, so clean contracts beat compatibility shims. Existing `kind: step` semantics remain unchanged: a step uses a local package agent.

TradingAgents source review used DeepWiki plus GitHub source evidence from TradingAgents HEAD `a5cb7cbd61d217fb0bc43f017392a861257afe6a`, then checked public README/changelog terminology through v0.2.5 from 2026-05-11.

## Current Owner Docs

This note keeps the research rationale only. Live implementation details now live in their owner documents:

| Topic | Owner doc |
|---|---|
| API routes, HTTP operation contract, run detail shape | `api-design.md` |
| Package-first platform behavior, Tools, Runs, UI contract | `signaldeck-agent-platform.md` |
| Platform-core memory and run evidence | `signaldeck-memory-layer-design.md` |
| Platform tables, including operation invocations | `data-model.md` |
| Validation scope | `test-plan.md` |

## Settled Outcome

SignalDeck kept the useful TradingAgents-inspired outcomes as general platform capabilities:

- Native runtime tools now cover finance-owned market data, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup, plus platform-core memory write/lookup.
- Platform-core memory now persists scoped entries, revisions, and run memory evidence while historical agent-memory reports stay report-domain history.
- A TradingAgents-style advisory research package remains demo/smoke package data, not a product-specific platform mode.
- `kind: http` is the shipped non-agent operation node, backed by package secret bindings, strict HTTP execution, `run_operation_invocations`, and operation cards in run detail.
- Advisory package outputs stay advisory-only. They may propose a portfolio decision but must not execute trades, draft brokerage operations, or add LangGraph checkpoint/runtime semantics.

## Rejected Scope

These remain rejected, even where TradingAgents supports adjacent behavior:

- LangGraph-compatible node, edge, checkpoint, and resume semantics.
- MCP-backed built-in data collection. MCP remains a user customization surface for Workflow Packages.
- Agent-initiated trading execution or automatic trade-operation drafts.
- Public memory APIs, dedicated memory tables, vector search, or embeddings for phase 1 memory.

## Remaining Comparison

| Area | TradingAgents | SignalDeck status | Fit |
|---|---|---|---|
| Runtime execution | LangGraph node execution with checkpoint resume. | Persisted Runs with steps, agent invocations, operation invocations, rerun, and step replay. Recovery and audit goals are similar, but runtime semantics are intentionally different. | Medium-High |
| Memory | Markdown decision log with automatic return/reflection updates and future prompt context. | Report-backed memory with pending outcome resolution, generated reflections, prompt snippets, and report audit links hidden from model-visible memory projections. | Medium-High |
| Analyst phase | Selected analysts, staged tool loops, bull/bear debate, research manager, trader, risk debate, and portfolio manager handoff. | Workflow Packages model this through authored `sequence`, `fanout`, `loop`, local agents, structured outputs, and package-local capability profiles. | Medium |
| External data/news/social research | Source-specific vendor data and news tools, plus Reddit and StockTwits sentiment paths. | Finance-owned native tools provide data, news, social sentiment, fundamentals, insider, position, and report context while `signaldeck.finance` is enabled. | Medium-High |
| True graph parity | Compiled LangGraph `StateGraph`, conditional edges, tool loops, and checkpoint behavior. | Rejected permanently because it would turn Workflow Packages into a LangGraph clone. | Rejected |
| Trading execution | Trading proposal and portfolio-manager approval/rejection in simulated-exchange framing. | Runs produce advice only; portfolio trading operations remain separate finance APIs. | Medium |

Filtered-out comparison rows include workflow container, agent roles, debate loops, shared state handoff, structured outputs, market/tool categories, auditability, and model configuration because SignalDeck reaches the practical runnable outcome through package, schema, tool, run, and model-connection surfaces.

Approximate remaining-gap fit after rejecting exact graph parity: 8/10 conceptual research-workflow match, 5/10 exact runtime/topology match, and 9/10 auditability match.

## Design Decisions That Survived

- Implement data, news, and social collection as native SignalDeck tools, never as TradingAgents-specific MCP presets.
- Keep trading output advisory-only.
- Use `kind: http` for the first non-agent operation node.
- Persist operation invocations separately from agent invocations.
- Keep package secrets referenced, encrypted, and redacted from exports, run details, diagnostics, and logs.
- Keep exact graph parity rejected permanently.

## Maintenance Rule

Do not re-expand this note into a duplicate route table, data model, validation plan, or implementation checklist. Merge live contract changes into the owner docs listed above, and keep this file limited to research provenance, comparison, and settled design rationale.
