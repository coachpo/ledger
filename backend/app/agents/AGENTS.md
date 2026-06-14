# BACKEND AGENTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers `app/agents/` only.

## OVERVIEW
`app/agents/` owns server-declared tool metadata, native runtime tool dispatch, and MCP execution boundaries. Extension registrars contribute extension-owned tool specs and executors, while `ExtensionService` decides which enabled extension keys reach `ToolCatalog`, `RuntimeToolRegistry`, execution providers, and run lifecycle hooks. This package keeps platform-owned memory tools separate from extension-owned tools and owns the safe MCP/runtime boundary.

Extension model: statically resident extension-contributed tools from Finance Workspace and Digital Oracle Runtime.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## STRUCTURE
```text
app/agents/
|-- tool_catalog/      # ToolCatalog and server-declared tool specs
|-- runtime_tools/     # native SignalDeck tool specs, parsers, executors, result models
`-- mcp/               # MCP config boundaries, security checks, snapshots, dispatch
```

## CHILD DOCS
- `tool_catalog/AGENTS.md` — server-declared tool metadata and package tool-key validation
- `runtime_tools/AGENTS.md` — core native runtime tools and extension-aware runtime registry
- `mcp/AGENTS.md` — saved MCP config safety, snapshots, adapter, and dispatch boundary

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Server-declared tools | `tool_catalog/AGENTS.md`, `tool_catalog/server_declared.py`, `../extensions/signaldeck_finance/tool_specs.py`, `../extensions/signaldeck_digital_oracle/tool_specs.py` | canonical platform memory tool keys plus extension-contributed keys, names, and descriptions |
| Capability tool-key validation | `tool_catalog/AGENTS.md`, `tool_catalog/__init__.py` | validates `toolKeys` against known server tools after enabled-extension filtering |
| Native registry | `runtime_tools/AGENTS.md`, `runtime_tools/__init__.py`, `runtime_tools/registry.py`, `../extensions/signaldeck_finance/runtime_executors.py`, `../extensions/signaldeck_digital_oracle/runtime_executors.py` | core plus extension OpenAI tool definitions and grant-checked dispatch |
| Core memory native tools | `runtime_tools/AGENTS.md`, `runtime_tools/memory.py` | platform-owned `signaldeck.memory.write` and `signaldeck.memory.lookup` parsers, access rules, executors, and result models |
| Extension runtime tools | `../extensions/signaldeck_finance/runtime_*`, `../extensions/signaldeck_digital_oracle/runtime_*` | Finance Workspace quotes/history/OHLCV/indicators/fundamentals/news/social sentiment/insider data, positions, and report lookup plus Digital Oracle prediction markets, SEC filings, and market sentiment |
| MCP runtime | `mcp/AGENTS.md`, `mcp/boundaries.py`, `mcp/security.py`, `mcp/runtime.py`, `mcp/tool_adapter.py` | saved config boundaries, URL/stdio safety, snapshots, dispatch |
| Integration points | `../services/extension_service.py`, `../services/agent_execution_service.py` | enabled-extension filtering, runtime dispatch, and execution wiring |
| Coverage | `../../tests/test_runtime_tools.py`, `../../tests/test_mcp_runtime.py`, `../../tests/test_workflow_package_preflight.py` | tool keys, MCP safety, memory outputs, and package capability validation |

## CONVENTIONS
- Core memory tool keys `signaldeck.memory.write` and `signaldeck.memory.lookup` are platform-owned, have OpenAI function names `signaldeck_memory_write` and `signaldeck_memory_lookup`, and must remain visible when all extensions are disabled.
- `ToolCatalog` and `RuntimeToolRegistry` must be built through extension-aware service wiring; do not construct alternate request-local registries that bypass enabled-extension filtering.
- Server-declared finance tool keys currently cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup. Server-declared Digital Oracle tool keys cover `signaldeck.prediction_markets.lookup`, `signaldeck.sec_filings.lookup`, and `signaldeck.market_sentiment.lookup` with unchanged OpenAI function names. Core memory tools are platform-owned.
- `signaldeck.reports.lookup` remains a finance-owned report lookup anchor. The retired report-backed memory write surface is not a live runtime tool; do not route new core memory behavior through finance registrars.
- Model-visible tool outputs must not expose report ids, slugs, names, raw markdown, URLs, downloads, or audit links. Runtime memory lookup output omits workflow visibility; runtime memory write output may expose `memoryId`, `revisionId`, `visibleToWorkflow`, revision action, provenance, and warnings.
- Runtime tools and prompt builders treat `memoryId` values as opaque platform-core memory identifiers.
- MCP boundary code owns URL/stdio safety, saved config normalization, snapshots, and dispatch wrapping; keep that safety logic here instead of scattering it through routes or services.
- Do not recreate a `skills/` namespace here; package-private skills are not a live backend app/agents contract.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not hard-code tool visibility outside `ExtensionService` filtering.
- Do not change tool keys or OpenAI function names without updating runtime tests, package validation, and any frontend references together.
- Do not route new memory-write behavior through finance report tools.
- Do not bypass MCP boundary/security helpers when dispatching saved configs.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_runtime_tools.py tests/test_mcp_runtime.py tests/test_workflow_package_preflight.py
```

## NOTES
- The live platform/server-declared tool contract is small: platform-owned memory tools plus extension-filtered finance market/report tools and Digital Oracle runtime tools.
- Most user-visible drift here shows up first in package preflight, runtime tool, or MCP tests rather than route handlers.
