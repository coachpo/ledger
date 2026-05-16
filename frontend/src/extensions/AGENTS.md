# FRONTEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers `src/extensions/` only.

## OVERVIEW
`src/extensions/` owns frontend extension registration, route assembly, sidebar grouping, extension-gated route shells, and tool-catalog filtering. The current bundled frontend extension is `signaldeck.finance`, enabled by backend state from `/api/extensions`.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## STRUCTURE
```text
src/extensions/
|-- runtime.tsx             # route/nav/tool filtering and disabled/loading shells
|-- registry.ts             # bundled frontend extension registry
|-- types.ts                # frontend extension contribution contracts
`-- signaldeck-finance/     # Finance Workspace contribution scaffold
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Runtime assembly | `runtime.tsx` | `assembleFinanceWorkspaceRoutes()`, `assembleNavGroups()`, `FinanceWorkspaceRouteGate`, tool filtering |
| Finance scaffold | `signaldeck-finance/scaffold.ts` | finance route/nav/API/tool discovery contributions and backend state source |
| Registry export | `registry.ts`, `index.ts` | bundled extension lookup and public exports |
| Backend state hooks | `../hooks/use-extensions.ts` | TanStack Query wrapper for `/api/extensions` |

## CONVENTIONS
- `runtime.tsx` is the only frontend layer that translates extension state into Finance Workspace route/nav visibility and tool filtering.
- Extension keys must match backend registry keys exactly; the bundled finance key is `signaldeck.finance`.
- Keep route contributions declarative in scaffolds and route gates generic in runtime.

## ANTI-PATTERNS
- Do not hard-code Finance Workspace visibility in `routes.ts`, `layout.tsx`, or page components.
- Do not add marketplace/install/remove behavior to frontend extension scaffolds in phase 1.
