# SIGNALDECK FINANCE EXTENSION GUIDE

> Inherits `/AGENTS.md`, `/backend/AGENTS.md`, and `/backend/app/extensions/AGENTS.md`. This file covers the statically resident `signaldeck.finance` extension only.

## OVERVIEW
`signaldeck_finance/` owns the current first-party Finance Workspace behavior: preserved `/api/v1` template/report routes, finance provider factories, finance grants/dependency records, finance runtime tools, and report lookup. Its public runtime tool keys are `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, and `signaldeck.finance.reports.lookup`. It does not own Digital Oracle prediction markets, SEC filings, or market sentiment runtime tools.

Treat this folder as extension-owned product logic, not as a staging area for generic platform behavior. If a finance-specific feature becomes a shared platform contract, move that ownership intentionally and update registries, gates, docs, and tests together.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Extension contract | `__init__.py`, `ownership.py` | `EXTENSION` export and canonical extension key |
| Dependency factories | `dependencies.py` | finance service/provider dependencies reused by route modules |
| Provider factories | `provider_factories.py` | deterministic/Yahoo quote providers plus Reddit/StockTwits social sentiment adapters |
| Grants and dependencies | `grant_policy.py`, `execution_dependencies.py` | runtime grant policy and dependency-only run records |
| Runtime tool specs | `tool_specs.py` | finance-owned server-declared tool metadata |
| Runtime executors | `runtime_executors.py`, `runtime_market_data.py`, `runtime_reports.py`, `runtime_types.py` | finance-owned OpenAI tool definitions, parser/executor modules, and typed runtime payloads |

## CONVENTIONS
- `FINANCE_WORKSPACE_EXTENSION_KEY` stays `signaldeck.finance` and is the owner key for finance routes, tools, and providers.
- Finance runtime tool keys use only the canonical `signaldeck.<owner>.<tool_collection>.<tool>` contract: `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, and `signaldeck.finance.reports.lookup`.
- OpenAI function names are mechanical underscore mappings from canonical keys, for example `signaldeck.finance.market_data.quote_lookup` -> `signaldeck_finance_market_data_quote_lookup`. Digital Oracle tool keys and function names belong to `signaldeck.digital_oracle`.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not move finance service factories back into generic API dependencies without preserving extension ownership.
- Do not promote finance-owned route, provider, tool, or report behavior into shared platform docs or core layers without an explicit shared-contract migration.
