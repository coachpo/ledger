# BACKEND AGENTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers `app/agents/` only.

## OVERVIEW
`app/agents/` owns server-declared tool metadata, native runtime tool dispatch, and MCP execution boundaries. Extension registrars contribute finance-owned tool specs and executors, but `ExtensionService` decides which enabled extension keys reach `ToolCatalog`, `RuntimeToolRegistry`, execution providers, and run lifecycle hooks. This package keeps platform-owned memory tools separate from finance-owned market/report tools and owns the safe MCP/runtime boundary.

Extension model: statically resident extension-contributed finance tools.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## STRUCTURE
```text
app/agents/
|-- tool_catalog/      # ToolCatalog and server-declared tool specs
|-- runtime_tools/     # native SignalDeck tool specs, parsers, executors, result models
`-- mcp/               # MCP config boundaries, security checks, snapshots, dispatch
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Server-declared tools | `tool_catalog/server_declared.py`, `../extensions/signaldeck_finance/tool_specs.py` | canonical platform memory tool keys plus extension-contributed keys, names, and descriptions |
| Capability tool-key validation | `tool_catalog/__init__.py` | validates `toolKeys` against known server tools after enabled-extension filtering |
| Native registry | `runtime_tools/__init__.py`, `runtime_tools/registry.py`, `../extensions/signaldeck_finance/runtime_executors.py` | core plus extension OpenAI tool definitions and grant-checked dispatch |
| Core memory native tools | `runtime_tools/memory.py` | platform-owned `signaldeck.memory.write` and `signaldeck.memory.lookup` parsers, access rules, executors, and result models |
| Finance runtime tools | `../extensions/signaldeck_finance/runtime_*` | finance-owned quotes/history/OHLCV/indicators/fundamentals/news/social sentiment/insider data, positions, and report lookup |
| MCP runtime | `mcp/boundaries.py`, `mcp/security.py`, `mcp/runtime.py`, `mcp/tool_adapter.py` | saved config boundaries, URL/stdio safety, snapshots, dispatch |
| Integration points | `../services/extension_service.py`, `../services/agent_execution_service.py` | enabled-extension filtering, runtime dispatch, and execution wiring |
| Coverage | `../../tests/test_runtime_tools.py`, `../../tests/test_mcp_runtime.py`, `../../tests/test_workflow_package_preflight.py` | tool keys, MCP safety, memory outputs, and package capability validation |

## CONVENTIONS
- Core memory tool keys `signaldeck.memory.write` and `signaldeck.memory.lookup` are platform-owned, have OpenAI function names `signaldeck_memory_write` and `signaldeck_memory_lookup`, and must remain visible when all extensions are disabled.
- `ToolCatalog` and `RuntimeToolRegistry` must be built through extension-aware service wiring; do not construct alternate request-local registries that bypass enabled-extension filtering.
- Server-declared finance tool keys currently cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup. Core memory tools are platform-owned.
- `signaldeck.reports.lookup` remains a finance-owned report lookup anchor. `signaldeck.reports.write` remains importable only as a retired fail-closed boundary; do not route new core memory behavior through finance registrars.
- Model-visible tool outputs must not expose report ids, slugs, names, raw markdown, URLs, downloads, or audit links. Runtime memory write output may expose `memoryId`, `revisionId`, status, revision action, provenance, and warnings.
- Runtime tools and prompt builders treat `memoryId` values as opaque platform-core memory identifiers.
- MCP boundary code owns URL/stdio safety, saved config normalization, snapshots, and dispatch wrapping; keep that safety logic here instead of scattering it through routes or services.
- Do not recreate a `skills/` namespace here; package-private skills are not a live backend app/agents contract.

## ANTI-PATTERNS
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
- The live platform/server-declared tool contract is small: platform-owned memory tools plus extension-filtered finance market/report tools.
- Most user-visible drift here shows up first in package preflight, runtime tool, or MCP tests rather than route handlers.
