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
| Runtime execution | LangGraph node execution with checkpoint resume. | Persisted Runs with steps, agent invocations, operation invocations, root-parameter rerun, invocation-input fork, and legacy step replay read lineage. Recovery and audit goals are similar, but runtime semantics are intentionally different. | Medium-High |
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

## Focused Gap Analysis: Indicators And Providers

This section narrows the remaining deltas relevant to reproducing TradingAgents-style advisory workflows in SignalDeck. It intentionally ignores broader runtime and topology differences and focuses only on indicator breadth and provider breadth inside `signaldeck.finance`.

| Area | What SignalDeck has | TradingAgents target | Gap | Solution proposal | Owner boundary | Key files | Priority |
|---|---|---|---|---|---|---|---|
| Indicator tool surface | `signaldeck.indicators.lookup` | TradingAgents-style technical-analysis tool | Contract is SMA-oriented | Keep tool key and widen schema | Runtime tool + finance extension | `backend/app/agents/runtime_tools/market_data.py`, `backend/app/extensions/signaldeck_finance/tool_specs.py` | High |
| Indicator inputs | `smaWindows` only | Curated MACD/RSI/Bollinger/ATR/EMA/VWMA-style set | No indicator selector | Add fixed `indicators` input | Runtime tool parser | `backend/app/agents/runtime_tools/market_data.py` | High |
| Indicator math | `close` + `sma_<window>` | Multi-indicator rows | No MACD/RSI/Bollinger path | Extend calculators in service layer | Market data service | `backend/app/services/market_data_service.py` | High |
| Indicator output model | Generic `values[]` rows | Generic multi-indicator rows | No real model gap | Reuse current output model | Runtime types | `backend/app/agents/runtime_tools/types.py` | Low |
| Quote/history/OHLCV provider | Yahoo or deterministic | Research-grade multi-provider coverage | Single real live backend | Add Alpha Vantage provider | Quote provider + factory | `backend/app/services/quote_provider.py`, `backend/app/extensions/signaldeck_finance/provider_factories.py` | High |
| Fundamentals provider | Tool exists | Real fundamentals coverage | Yahoo path returns unavailable | Implement Alpha Vantage fundamentals | Quote provider | `backend/app/services/quote_provider.py` | High |
| News provider | Yahoo-backed news | Broader provider parity | No Alpha Vantage news path | Add Alpha Vantage news adapter and fallback | Quote provider + service | `backend/app/services/quote_provider.py`, `backend/app/services/market_data_service.py` | Medium |
| Insider provider | Tool exists | Real insider coverage | Yahoo path returns unavailable | Implement Alpha Vantage insider path | Quote provider | `backend/app/services/quote_provider.py` | High |
| Social sentiment provider | Reddit + StockTwits | TradingAgents-adjacent sentiment coverage | Narrow but acceptable | Keep as-is unless expansion is needed | Social sentiment service | `backend/app/services/social_sentiment_provider.py`, `backend/app/extensions/signaldeck_finance/provider_factories.py` | Low |
| Provider selection | `QUOTE_PROVIDER_BACKEND=yahoo|deterministic` | Multi-provider or fallback strategy | Config too narrow | Add `alpha_vantage` or ordered provider config | Core config + factory | `backend/app/core/config.py`, `backend/app/extensions/signaldeck_finance/provider_factories.py` | High |
| Service fallback | Fallback helper exists | Real provider chain | Capability exists but DI does not use it | Feed ordered providers into fundamentals/news/insider | Market data service + finance DI | `backend/app/services/market_data_service.py`, `backend/app/extensions/signaldeck_finance/dependencies.py` | Medium |
| Test coverage | Runtime/service tests exist | Safe extension growth | Missing parity coverage | Add indicator/provider regression tests | Backend tests | `backend/tests/test_runtime_tools.py`, `backend/tests/test_market_data_service.py` | High |

## Maintenance Rule

Do not re-expand this note into a duplicate route table, data model, validation plan, or implementation checklist. Merge live contract changes into the owner docs listed above, and keep this file limited to research provenance, comparison, and settled design rationale.
