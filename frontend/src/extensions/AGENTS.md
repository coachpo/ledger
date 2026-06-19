# FRONTEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers `src/extensions/` only.

## OVERVIEW
`src/extensions/` owns frontend extension registration, route assembly, sidebar grouping, extension-gated route shells, and tool-catalog filtering. The current bundled frontend extensions are Finance Workspace and Digital Oracle Runtime.

`signaldeck.finance` is enabled by backend state from `/api/extensions`.

`signaldeck.digital_oracle` is enabled by backend state from `/api/extensions` and is tool-only in this upgrade.

Extension model: this folder owns statically resident frontend extension registration, route assembly, sidebar grouping, extension-gated route shells, and tool-catalog filtering.

Future upgrade work must keep this folder focused on generic extension-runtime wiring. Finance-specific route/nav/tool behavior should stay in the statically resident finance scaffold until a shared platform contract is explicit.

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
|-- runtime.tsx             # loading/disabled route shells and gate components
|-- runtime-helpers.ts      # route assembly, nav grouping, and extension-filtered tool helpers
|-- registry.ts             # bundled frontend extension registry
|-- types.ts                # private frontend route/nav/tool gate contracts
|-- signaldeck-finance/          # Finance Workspace route/nav/tool scaffold
`-- signaldeck-digital-oracle/   # Digital Oracle tool-only scaffold
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Runtime gates and shells | `runtime.tsx` | `FinanceWorkspaceRouteGate`, loading/disabled shells, and backend-state gating UI |
| Runtime assembly | `runtime-helpers.ts` | `assembleFinanceWorkspaceRoutes()`, `assembleNavGroups()`, and `filterToolsForExtensionState()` |
| Finance scaffold | `signaldeck-finance/scaffold.ts` | finance route/nav/tool entries and private backend-state gate tags |
| Digital Oracle scaffold | `signaldeck-digital-oracle/scaffold.ts` | Digital Oracle canonical tool keys only, with no route or nav contributions |
| Registry export | `registry.ts`, `index.ts` | statically resident extension lookup and public exports |
| Backend state hooks | `../hooks/use-extensions.ts` | TanStack Query wrapper for `/api/extensions` |
| Route-state surface | `../pages/extensions/AGENTS.md` | `/extensions` page consumes the slim backend contract, not scaffold metadata |

## CONVENTIONS
- `runtime.tsx` owns gate components and loading/disabled shells; `runtime-helpers.ts` owns route assembly, nav grouping, and extension-filtered tool helpers.
- Extension keys must match backend registry keys exactly; the bundled keys are `signaldeck.finance` and `signaldeck.digital_oracle`.
- Keep route/nav/tool entries declarative in scaffolds and route gates generic in runtime. Digital Oracle stays tool-only here with canonical tool keys `signaldeck.digital_oracle.prediction_markets.lookup`, `signaldeck.digital_oracle.sec_filings.lookup`, `signaldeck.digital_oracle.market_sentiment.lookup`, `signaldeck.digital_oracle.macro_rates.lookup`, `signaldeck.digital_oracle.crypto_derivatives.lookup`, `signaldeck.digital_oracle.cftc_positioning.lookup`, and `signaldeck.digital_oracle.options.lookup`; OpenAI function names are the mechanical underscore mappings of those keys. There are no route or nav entries.
- Private gate tags such as `requiredExtensionKey` are frontend wiring only. Do not mirror backend registry metadata or expose scaffold details as public state.
- The `/extensions` route renders only the slim backend contract. Page/layout code must not recreate scaffold or registry logic that belongs here.

## ANTI-PATTERNS
- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not hard-code Finance Workspace visibility in `routes.ts`, `layout.tsx`, or page components.
- Do not add marketplace/install/remove behavior to frontend extension scaffolds in phase 1.
- Do not add plugin-manifest fields to frontend extension state, run types, route gates, or docs.
- Do not migrate finance-specific route/nav/tool assumptions into generic runtime wiring without first defining the shared platform contract.
