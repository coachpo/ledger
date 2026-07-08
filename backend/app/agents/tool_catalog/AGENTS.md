# BACKEND TOOL CATALOG GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/agents/AGENTS.md`.

## OVERVIEW
`app/agents/tool_catalog/` owns read-only server-declared tool metadata and package capability-profile validation. It resolves known tool keys after enabled-extension filtering and exposes the slim `/api/tools` contract through backend services/routes.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Catalog behavior | `__init__.py` | `ToolCatalog`, enabled filtering, duplicate/unknown key validation |
| Server tools | `server_declared.py` | extension-contributed metadata registry |
| API route | `../../api/tools.py` | read-only `/api/tools` response |
| Service wiring | `../../services/extension_service.py`, `../../api/dependencies.py` | builds catalog with enabled extension keys |
| Coverage | `../../../tests/test_tool_catalog_api.py`, `../../../tests/test_workflow_package_preflight.py` | slim public tool shape and package tool-key validation |

## CONVENTIONS
- Public tool metadata is intentionally small: `key`, `displayName`, and `description`.
- Public tool keys are canonical `signaldeck.<owner>.<tool_collection>.<tool>` strings only. Live extension-owned keys include `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, `signaldeck.finance.reports.lookup`, `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, and `signaldeck.digital_oracle.market_sentiment.lookup`.
- Known tools include bundled extension contributions.
- Disabled extensions hide their server-declared tools from registered-tool lists while still allowing known-tool dependency analysis where explicitly needed.
- Capability profile validation reports field-indexed details for unknown, duplicate, or disabled tool keys.
- Keep schema/output formatting in `app/schemas/tool.py`; the catalog should not hand-build camelCase API payloads.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not expose module names, owner extension keys, registrar paths, scaffold metadata, or plugin-manifest fields through `/api/tools`.
- Do not validate package `toolKeys` against an unfiltered catalog when enabled-extension state matters.
- Do not duplicate tool-key normalization in route handlers or frontend code, and do not introduce ownerless aliases or legacy compatibility keys.

## VALIDATION
```bash
cd backend
uv run pytest tests/test_tool_catalog_api.py tests/test_workflow_package_preflight.py
```
