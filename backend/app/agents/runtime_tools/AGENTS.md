# BACKEND RUNTIME TOOLS GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/agents/AGENTS.md`.

## OVERVIEW
`app/agents/runtime_tools/` owns platform-owned native runtime tool contracts plus the registry that combines core tools with extension-contributed specs. Core memory tools live here; finance and Digital Oracle tool implementations stay in their extension folders and register through private extension registrars.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Registry | `registry.py`, `__init__.py` | enabled-extension filtering, descriptors, OpenAI tools, dispatch lookup |
| Runtime spec types | `types.py`, `declarations.py` | tool spec, context, warnings, model-facing declarations |
| Failure taxonomy | `failure_taxonomy.py` | typed retryable/non-retryable runtime failure categories |
| Platform memory tools | `memory.py` | `signaldeck.core.memory.write` and `signaldeck.core.memory.lookup` parsers/executors/results |
| Extension boundaries | `market_data.py`, `positions.py`, `reports.py` | import/export boundaries for extension-owned implementations; not public compatibility aliases |
| Coverage | `../../../tests/test_runtime_tools.py`, `../../../tests/test_workflow_package_preflight.py` | tool keys, OpenAI function names, access checks, package validation |

## CONVENTIONS
- Core memory tool keys `signaldeck.core.memory.write` and `signaldeck.core.memory.lookup` are platform-owned, map to `signaldeck_core_memory_write` and `signaldeck_core_memory_lookup`, and must remain available when bundled extensions are disabled.
- All public runtime tool keys use the canonical `signaldeck.<owner>.<tool_collection>.<tool>` scheme; extension-owned tool specs keep their implementations in `app/extensions/<extension>/runtime_*` and register through private extension registrars.
- `RuntimeToolRegistry` is the only place that converts granted tool keys into model declarations and dispatch descriptors.
- Parsers should reject malformed JSON/unsupported fields with `RuntimeToolError` before provider dispatch.
- Runtime outputs shown to models must stay narrow; memory lookup output omits workflow visibility, while memory write output may expose memory/revision ids, `visibleToWorkflow`, provenance, and warnings only.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not hard-code tool visibility outside enabled-extension filtering.
- Do not move finance or Digital Oracle executors into this core folder.
- Do not add raw provider payloads, report markdown, report slugs, or audit URLs to model-visible runtime output.
- Do not change tool keys or OpenAI function names without backend runtime, package validation, and frontend tool-picker updates.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_runtime_tools.py tests/test_workflow_package_preflight.py tests/test_tool_catalog_api.py
```
