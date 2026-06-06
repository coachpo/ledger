# SIGNALDECK FINANCE EXTENSION GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/extensions/AGENTS.md`. This file covers the statically resident `signaldeck.finance` extension only.

## OVERVIEW
`signaldeck_finance/` owns the current first-party Finance Workspace behavior: preserved `/api/v1` portfolio/template/report routes, finance provider factories, finance runtime tools, report lookup, and historical agent-memory report readers. It does not own Digital Oracle prediction markets, SEC filings, or market sentiment runtime tools.

Treat this folder as extension-owned product logic, not as a staging area for generic platform behavior. If a finance-specific feature becomes a shared platform contract, move that ownership intentionally and update registries, gates, docs, and tests together.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Extension identity | `ownership.py` | canonical extension key and label |
| Route registration | `api_routers.py` | finance `/api/v1` router list and `require_extension_enabled()` dependencies |
| Dependency factories | `dependencies.py` | finance service/provider dependencies reused by route modules |
| Provider factories | `provider_factories.py` | deterministic/Yahoo quote providers plus Reddit/StockTwits social sentiment adapters |
| Runtime tool specs | `tool_specs.py` | finance-owned server-declared tool metadata |
| Runtime executors | `runtime_executors.py` | finance-owned OpenAI tool definitions and dispatch grants |
| Report hooks | `hooks.py` | report lookup, template placeholder, and return-resolution ownership hooks; core memory is platform-owned |

## CONVENTIONS
- `FINANCE_WORKSPACE_EXTENSION_KEY` stays `signaldeck.finance` and is the owner key for finance routes, tools, providers, and hooks.
- Finance route registrations must remain guarded by `require_extension_enabled()`.
- Finance runtime tool keys and OpenAI function names stay stable while their specs and executors are registered through this extension. Digital Oracle tool keys and OpenAI function names also stay stable, but their specs and executors belong to `signaldeck.digital_oracle`.

## ANTI-PATTERNS
- Do not move finance service factories back into generic API dependencies without preserving extension ownership and gating.
- Do not promote finance-owned route, provider, tool, or report behavior into shared platform docs or core layers without an explicit shared-contract migration.
- Do not expose quote, social sentiment, report lookup, or finance route behavior when `signaldeck.finance` is disabled.
