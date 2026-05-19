# BACKEND AGENTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers `app/agents/` only.

## OVERVIEW
`app/agents/` owns server-declared tools, native runtime tool dispatch, and MCP execution boundaries. Extension registrars contribute finance-owned tool specs, while services decide which enabled extension/capability grants tool access; this package defines the tool catalog host, native tool registry, OpenAI function payloads, MCP boundary checks, snapshots, and safe output wrapping.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## STRUCTURE
```text
app/agents/
|-- tool_catalog/      # ToolCatalog and server-declared tool specs
|-- runtime_tools/     # native SignalDeck tool specs, parsers, executors, result models
|-- mcp/               # MCP config boundaries, security checks, snapshots, dispatch
`-- skills/            # retired namespace, not a live capability contract
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Server-declared tools | `tool_catalog/server_declared.py`, `../extensions/signaldeck_finance/tool_specs.py` | canonical core SignalDeck tool keys plus extension-contributed keys, names, and descriptions |
| Capability tool-key validation | `tool_catalog/__init__.py` | validates `toolKeys` against known server tools after enabled-extension filtering |
| Native registry | `runtime_tools/__init__.py`, `runtime_tools/registry.py`, `../extensions/signaldeck_finance/runtime_executors.py` | core plus extension OpenAI tool definitions and grant-checked dispatch |
| Core memory native tools | `runtime_tools/memory.py` | platform-owned `signaldeck.memory.write` and `signaldeck.memory.lookup` parsers, grant policies, executors, and result models |
| Financial native tools | `../extensions/signaldeck_finance/runtime_*` | finance-owned quotes/history/OHLCV/indicators/fundamentals/news/social sentiment/insider data, positions, report lookup, and retired report-write boundary |
| MCP runtime | `mcp/boundaries.py`, `mcp/security.py`, `mcp/runtime.py`, `mcp/tool_adapter.py` | saved config boundaries, URL/stdio safety, snapshots, dispatch |

## CONVENTIONS
- Core memory tool keys `signaldeck.memory.write` and `signaldeck.memory.lookup` are platform-owned, have OpenAI function names `signaldeck_memory_write` and `signaldeck_memory_lookup`, and must remain visible when all extensions are disabled.
- Server-declared finance tool keys currently cover market quote/history/OHLCV, indicators, fundamentals, news, social sentiment, insider data, positions, and report lookup; `ExtensionService` filters visibility by enabled extension keys. Core memory tools are platform-owned.
- `signaldeck.reports.lookup` remains a finance-owned report lookup anchor. `signaldeck.reports.write` remains importable only as a retired fail-closed boundary; do not route new core memory behavior through finance registrars.
- Model-visible tool outputs must not expose report ids, slugs, names, raw markdown, URLs, downloads, or audit links. Runtime memory write output may expose `memoryId`, `revisionId`, status, revision action, provenance, and warnings.
- Runtime tools and prompt builders treat `memoryId` values as opaque. Only `ReportBackedMemoryStore` may parse the legacy `mem_<report_id>` format.
