# FRONTEND EXTENSIONS GUIDE

> Inherits `/AGENTS.md` and `/frontend/AGENTS.md`. This file covers `src/extensions/` only.

## OVERVIEW
`src/extensions/` owns frontend extension registration, route assembly, sidebar grouping, extension-gated route shells, and tool-catalog filtering. The current bundled frontend extension is `signaldeck.finance`, enabled by backend state from `/api/extensions`.

Future upgrade work must keep this folder focused on generic extension-runtime wiring. Finance-specific route/nav/tool behavior should stay in the bundled finance scaffold until a shared platform contract is explicit.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## STRUCTURE
```text
src/extensions/
|-- runtime.tsx             # route/nav/tool filtering and disabled/loading shells
|-- registry.ts             # bundled frontend extension registry
|-- types.ts                # private frontend route/nav/tool gate contracts
`-- signaldeck-finance/     # Finance Workspace route/nav/tool scaffold
```

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Runtime assembly | `runtime.tsx` | `assembleFinanceWorkspaceRoutes()`, `assembleNavGroups()`, `FinanceWorkspaceRouteGate`, tool filtering |
| Finance scaffold | `signaldeck-finance/scaffold.ts` | finance route/nav/tool entries and private backend-state gate tags |
| Registry export | `registry.ts`, `index.ts` | bundled extension lookup and public exports |
| Backend state hooks | `../hooks/use-extensions.ts` | TanStack Query wrapper for `/api/extensions` |

## CONVENTIONS
- `runtime.tsx` is the only frontend layer that translates extension state into Finance Workspace route/nav visibility and tool filtering.
- Extension keys must match backend registry keys exactly; the bundled finance key is `signaldeck.finance`.
- Keep route/nav/tool entries declarative in scaffolds and route gates generic in runtime.
- Private gate tags such as `requiredExtensionKey` are frontend wiring only. Do not mirror backend registry metadata or expose scaffold details as public state.

## ANTI-PATTERNS
- Do not hard-code Finance Workspace visibility in `routes.ts`, `layout.tsx`, or page components.
- Do not add marketplace/install/remove behavior to frontend extension scaffolds in phase 1.
- Do not add plugin-manifest fields to frontend extension state, run types, route gates, or docs.
- Do not migrate finance-specific route/nav/tool assumptions into generic runtime wiring without first defining the shared platform contract.
