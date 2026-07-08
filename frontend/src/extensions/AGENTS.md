# FRONTEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers `src/extensions/` only.

## OVERVIEW
`src/extensions/` is a transitional frontend extension host scheduled for Task 5.3 removal. Do not extend route assembly, sidebar grouping, extension-gated route shells, or tool-catalog filtering here.

`signaldeck.finance` is statically installed on the backend and owns template/report routes plus runtime tools there.

`signaldeck.digital_oracle` is statically installed on the backend and is tool-only in this upgrade.

Extension model: backend extension contributions come from `INSTALLED_EXTENSIONS`; this frontend folder is stale cleanup scope.

Future upgrade work should remove this folder per Task 5.3 and inline the remaining template/report routes into static routing.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## STRUCTURE
```text
src/extensions/
|-- runtime.tsx             # stale loading/disabled shells pending deletion
|-- runtime-helpers.ts      # stale route/nav/tool helpers pending deletion
|-- registry.ts             # stale frontend extension registry pending deletion
|-- types.ts                # stale frontend route/nav/tool contracts pending deletion
|-- signaldeck-finance/          # stale Finance Workspace scaffold pending deletion
`-- signaldeck-digital-oracle/   # stale Digital Oracle scaffold pending deletion
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Runtime gates and shells | `runtime.tsx` | stale `FinanceWorkspaceRouteGate` and disabled shells pending deletion |
| Runtime assembly | `runtime-helpers.ts` | stale `assembleFinanceWorkspaceRoutes()`, `assembleNavGroups()`, and filtering helpers pending deletion |
| Finance scaffold | `signaldeck-finance/scaffold.ts` | stale finance route/nav/tool entries pending deletion |
| Digital Oracle scaffold | `signaldeck-digital-oracle/scaffold.ts` | Digital Oracle canonical tool keys only, with no route or nav contributions |
| Registry export | `registry.ts`, `index.ts` | statically resident extension lookup and public exports |
| Backend state hooks | `../hooks/use-extensions.ts` | stale hook pending deletion |
| Route-state surface | `../pages/extensions/AGENTS.md` | stale `/extensions` page pending deletion |

## CONVENTIONS
- Do not add new gate components, disabled shells, route assembly, nav grouping, or tool filtering here.
- Extension keys must match backend registry keys exactly; the bundled keys are `signaldeck.finance` and `signaldeck.digital_oracle`.
- Keep route/nav/tool entries declarative in scaffolds and route gates generic in runtime. Digital Oracle stays tool-only here with canonical tool keys `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`; OpenAI function names are the mechanical underscore mappings of those keys. There are no route or nav entries.
- Private gate tags such as `requiredExtensionKey` are stale frontend wiring only. Do not mirror backend registry metadata or expose scaffold details as public state.
- The backend no longer exposes extension state; page/layout code must not recreate frontend scaffold or registry logic.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add new Finance Workspace visibility logic in `routes.ts`, `layout.tsx`, or page components; Task 5.3 inlines remaining routes statically.
- Do not add marketplace/install/remove behavior to frontend extension scaffolds in phase 1.
- Do not add plugin-manifest fields to frontend state, run types, route gates, or docs.
- Do not migrate finance-specific route/nav/tool assumptions into generic runtime wiring without first defining the shared platform contract.
