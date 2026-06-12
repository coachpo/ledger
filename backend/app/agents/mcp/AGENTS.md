# BACKEND MCP GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/agents/AGENTS.md`.

## OVERVIEW
`app/agents/mcp/` owns the safe boundary between Workflow Package private MCP configs and runtime tool execution. It validates saved client boundaries, checks URL/stdio safety, snapshots available MCP tools, adapts tool schemas to execution descriptors, dispatches calls, and redacts unsafe output for model-visible results.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Boundary construction | `boundaries.py` | saved config boundary model and connection testing |
| Runtime dispatch | `runtime.py` | tool discovery, dispatcher construction, execution, result/error shaping |
| Security checks | `security.py` | URL and stdio validation rules |
| Tool adapter | `tool_adapter.py` | MCP tool snapshots to execution descriptors |
| Integration | `../../services/mcp_server_service.py`, `../../services/agent_execution_service.py` | saved config tests and runtime execution wiring |
| Coverage | `../../../tests/test_mcp_runtime.py`, `../../../tests/test_workflow_package_preflight.py` | MCP safety, snapshots, preflight dependency checks |

## CONVENTIONS
- MCP configs are package-private runtime dependencies; do not recreate global live MCP authoring routes.
- URL/stdio validation belongs in `security.py`; routes/services should not duplicate or weaken those checks.
- Runtime results must be safe for model consumption: redact long or sensitive MCP text and preserve tool/server identifiers for auditability.
- MCP tool schemas are adapter output, not hand-built OpenAI schemas scattered through execution services.
- Failed MCP calls should surface typed runtime errors/warnings; do not swallow transport failures or return raw exception objects.

## ANTI-PATTERNS
- Do not bypass boundary/security helpers when testing or dispatching saved MCP configs.
- Do not expose package-private MCP secrets, env values, headers, or query values in model-visible output.
- Do not add marketplace/global MCP server behavior under this package.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_mcp_runtime.py tests/test_workflow_package_preflight.py
```
