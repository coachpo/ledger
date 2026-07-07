# BACKEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/backend/AGENTS.md`. This file covers bundled backend extension infrastructure.

## OVERVIEW
`app/extensions/` owns first-party extension registration, private registrar wiring, and extension-owned composition roots. The current statically resident bundled extensions are Finance Workspace and Digital Oracle Runtime.

`signaldeck.finance` owns preserved finance `/api/v1` routers, finance provider factories, finance service gates/grants/dependency records, finance runtime tool specs/executors, split runtime modules for market data/positions/reports, report lookup, and historical agent-memory report readers. Its public runtime tool keys are `signaldeck.finance.market_data.quote_lookup`, `signaldeck.finance.market_data.history_lookup`, `signaldeck.finance.market_data.ohlcv_lookup`, `signaldeck.finance.indicators.lookup`, `signaldeck.finance.fundamentals.lookup`, `signaldeck.finance.news.lookup`, `signaldeck.finance.social_sentiment.lookup`, `signaldeck.finance.insider_data.lookup`, `signaldeck.finance.positions.lookup`, and `signaldeck.finance.reports.lookup`.

`signaldeck.digital_oracle` owns only `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup` in this upgrade.

Extension model: this folder owns statically resident extension registration, private registrar wiring, and extension-owned composition roots for code shipped with SignalDeck Core.

Future upgrade work must preserve the boundary between generic extension infrastructure in this folder and extension-owned behavior in `signaldeck_finance/` and `signaldeck_digital_oracle/`. Move behavior across those seams only when the shared platform contract is explicit and the registries, docs, and tests move with it.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## CHILD DOCS
- `signaldeck_finance/AGENTS.md` — statically resident `signaldeck.finance` ownership, route registrations, provider factories, service gates/grants, split runtime modules, report lookup, and historical agent-memory report readers
- `signaldeck_digital_oracle/AGENTS.md` — statically resident `signaldeck.digital_oracle` tool-only runtime ownership

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Bundled registry | `registry.py` | extension identity, initial enabled seed, and private registrar references |
| Extension package exports | `__init__.py` | statically resident extension registry exports |
| Finance extension | `signaldeck_finance/AGENTS.md` | current first-party finance workspace extension |
| Digital Oracle extension | `signaldeck_digital_oracle/AGENTS.md` | tool-only prediction markets, SEC filings, market sentiment, macro rates, crypto derivatives, CFTC positioning, and options runtime extension |
| Service state/filtering | `../services/extension_service.py` | persisted slim state plus ToolCatalog/runtime registry filtering |
| API state | `../api/extensions.py` | `/api/extensions` list/toggle route family |
| DB state | `../models/extension.py` | `extension_states` persistence |

## CONVENTIONS
- Extension definitions are private registry wiring; behavior is supplied through explicit registrars and service-layer filtering.
- Extension-owned public runtime tool keys must use the canonical `signaldeck.<owner>.<tool_collection>.<tool>` scheme listed above; do not define ownerless aliases.
- `ExtensionService` is the authority for persisted state, `/api/extensions` toggles, and enabled ToolCatalog/runtime views.
- Public extension state stays slim: `key`, `label`, and `enabled` only. Keep registrar paths, owner keys, scaffold details, and plugin-manifest-style fields private.
- During upstream migrations, provider/data lookup functions belong in the owning extension's provider wrappers, runtime tool specs/executors, and ToolCatalog metadata. Same or similar lookup functions from different upstream repos stay separate obligations unless a product decision intentionally narrows or merges them.

## ANTI-PATTERNS
- Do not add auth middleware, RBAC, tenant/account ownership columns, permission checks, or account-management APIs unless the product scope changes.
- Do not import extension-owned dependencies directly from generic platform services when `ExtensionService` should filter by enabled state.
- Do not add plugin marketplace, install, or remove semantics to statically resident extension state in phase 1.
- Do not expose registry/scaffold metadata through `/api/extensions`, `/api/tools`, OpenAPI, run dependency records, or docs.
- Do not migrate finance-owned routing, provider, or runtime-tool behavior into generic extension infrastructure without first defining the shared platform contract.
