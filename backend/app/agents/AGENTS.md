# BACKEND AGENTS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers `app/agents/` only.

## OVERVIEW
`app/agents/` owns server-declared tools, native runtime tool dispatch, and MCP execution boundaries. Services decide when capabilities grant tool access; this package defines the tool catalog, native tool registry, OpenAI function payloads, MCP boundary checks, snapshots, and safe output wrapping.

## STRUCTURE
```text
app/agents/
|-- tool_catalog/      # ToolCatalog and server-declared tool specs
|-- runtime_tools/     # native Ledger tool specs, parsers, executors, result models
|-- mcp/               # MCP config boundaries, security checks, snapshots, dispatch
`-- skills/            # retired namespace, not a live capability contract
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Server-declared tools | `tool_catalog/server_declared.py` | canonical Ledger tool keys, names, descriptions |
| Capability tool-key validation | `tool_catalog/__init__.py` | validates `toolKeys` against known server tools |
| Native registry | `runtime_tools/__init__.py`, `runtime_tools/registry.py` | OpenAI tool definitions and grant-checked dispatch |
| Financial native tools | `runtime_tools/market_data.py`, `runtime_tools/positions.py`, `runtime_tools/reports.py` | quotes/history, positions, report lookup, memory-report writes |
| MCP runtime | `mcp/boundaries.py`, `mcp/security.py`, `mcp/runtime.py`, `mcp/tool_adapter.py` | saved config boundaries, URL/stdio safety, snapshots, dispatch |

## CONVENTIONS
- `ledger.reports.lookup` and `ledger.reports.write` remain the stable server tool keys in phase 1. Their OpenAI function names, `ledger_reports_lookup` and `ledger_reports_write`, are compatibility anchors, not legacy debt to rename now.
- Phase 1 does not expose `ledger.memory.*` tool keys. Keep report lookup report-shaped, and keep report memory writes memory-shaped while preserving the report tool key and function name.
- Model-visible tool outputs must not expose report ids, slugs, names, raw markdown, URLs, downloads, or audit links. Runtime write output may expose `memoryId`, status, summary, provenance, and warnings; API/UI projections can add nested `auditLinks.report` after the model call.
- Runtime tools and prompt builders treat `memoryId` values as opaque. Only `ReportBackedMemoryStore` may parse the phase 1 `mem_<report_id>` format.
