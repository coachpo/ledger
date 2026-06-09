# BACKEND TOOL CATALOG GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/agents/AGENTS.md`.

## OVERVIEW
`app/agents/tool_catalog/` owns read-only server-declared tool metadata and package capability-profile validation. It resolves known tool keys after enabled-extension filtering and exposes the slim `/api/tools` contract through backend services/routes.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Catalog behavior | `__init__.py` | `ToolCatalog`, enabled filtering, duplicate/unknown key validation |
| Server tools | `server_declared.py` | platform memory tool specs plus extension-contributed metadata registry |
| API route | `../../api/tools.py` | read-only `/api/tools` response |
| Service wiring | `../../services/extension_service.py`, `../../api/dependencies.py` | builds catalog with enabled extension keys |
| Coverage | `../../../tests/test_tool_catalog_api.py`, `../../../tests/test_workflow_package_preflight.py` | slim public tool shape and package tool-key validation |

## CONVENTIONS
- Public tool metadata is intentionally small: `key`, `displayName`, and `description`.
- Known tools include platform-owned memory tools plus bundled extension contributions.
- Disabled extensions hide their server-declared tools from registered-tool lists while still allowing known-tool dependency analysis where explicitly needed.
- Capability profile validation reports field-indexed details for unknown, duplicate, or disabled tool keys.
- Keep schema/output formatting in `app/schemas/tool.py`; the catalog should not hand-build camelCase API payloads.

## ANTI-PATTERNS
- Do not expose module names, owner extension keys, registrar paths, scaffold metadata, or plugin-manifest fields through `/api/tools`.
- Do not validate package `toolKeys` against an unfiltered catalog when enabled-extension state matters.
- Do not duplicate tool-key normalization in route handlers or frontend code.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_tool_catalog_api.py tests/test_workflow_package_preflight.py
```
