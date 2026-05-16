# SIGNALDECK FINANCE EXTENSION GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/extensions/AGENTS.md`. This file covers the bundled `signaldeck.finance` extension only.

## OVERVIEW
`signaldeck_finance/` owns the current first-party Finance Workspace contribution: preserved `/api/v1` portfolio/template/report routes, finance provider factories, finance runtime tools, frontend/docs ownership metadata, and report-backed memory hooks.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Extension identity | `ownership.py` | canonical extension key, label, phase, contribution inventory, route/tool ownership metadata |
| Route registration | `api_routers.py` | finance `/api/v1` router list and `require_extension_enabled()` dependencies |
| Dependency factories | `dependencies.py` | finance service/provider dependencies reused by route modules |
| Provider factories | `provider_factories.py` | deterministic/Yahoo quote providers plus Reddit/StockTwits social sentiment adapters |
| Runtime tool specs | `tool_specs.py` | finance-owned server-declared tool metadata |
| Runtime executors | `runtime_executors.py` | finance-owned OpenAI tool definitions and dispatch grants |
| Report/memory hooks | `hooks.py` | report-backed memory, follow-up, context, template placeholder, and return-resolution ownership hooks |
| Scaffold/docs metadata | `scaffold.py`, `docs.py` | bundled extension scaffold and documentation contribution metadata |

## CONVENTIONS
- `FINANCE_WORKSPACE_EXTENSION_KEY` stays `signaldeck.finance` and is the owner key for finance routes, tools, providers, and hooks.
- Finance route registrations must remain guarded by `require_extension_enabled()`.
- Runtime tool keys and OpenAI function names stay stable even though their metadata is contributed by this extension.

## ANTI-PATTERNS
- Do not move finance service factories back into generic API dependencies without preserving extension ownership and gating.
- Do not expose quote, social sentiment, report-memory, or finance route behavior when `signaldeck.finance` is disabled.
