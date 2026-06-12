# FRONTEND EXTENSIONS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/extensions/` owns the `/extensions` system route: a slim statically resident extension inventory that renders backend state, sorts labels/keys for stable display, and toggles enablement through the shared extension hooks. This is a state surface, not a marketplace or plugin-management UI.

Extension model: statically resident extension inventory.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task              | Location                                                                                            | Notes                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Extensions route  | `list.tsx`                                                                                          | slim extension inventory, status badges, toggle actions, and route-level loading/error/empty states |
| State hooks       | `../../hooks/use-extensions.ts`                                                                     | `/api/extensions` reads, toggles, tool-cache invalidation, and finance-only cache invalidation      |
| Runtime ownership | `../../extensions/AGENTS.md`, `../../extensions/runtime.tsx`, `../../extensions/runtime-helpers.ts` | runtime route gates, nav assembly, and tool filtering remain outside the page layer                 |
| Route coverage    | `list.test.tsx`                                                                                     | route rendering, toggle behavior, and bundled-state expectations                                    |

## CONVENTIONS

- Render only the backend extension contract: `key`, `label`, and `enabled`.
- Keep sorting, toast feedback, and route-level empty/error/loading states in `list.tsx`; keep request policy and invalidation in `use-extensions.ts`.
- Use `PlatformResourceList` and `PlatformResourceCard` for the inventory shell so this page stays visually aligned with other platform/system routes.
- Treat this page as a system state surface only. Route/nav/tool visibility still belongs to the extension runtime layer.
- Keep `/extensions` aligned with `systemState` route metadata: scroll shell, `route-extensions` main, loading/ready/error/empty states, and no extension-owned disabled route shell.
- Regression coverage must include enabled, disabled, and re-enabled Finance Workspace states for sidebar nav and direct finance routes, plus mixed Finance Workspace and Digital Oracle states for tool authoring discovery. Digital Oracle must remain route-less and nav-less.

## ANTI-PATTERNS

- Do not add marketplace, install, remove, or contribution-browser behavior here in phase 1.
- Do not mirror private registry or scaffold metadata in the UI.
- Do not bypass `useToggleExtension()` or duplicate finance visibility rules in the page layer.
- Do not turn this route into a generic settings dump unrelated to statically resident extension state.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/extensions/list.test.tsx
```

## NOTES

- This folder currently contains one live route file; keep related behavior here until the extension state surface splits into additional route families.
- Changes here usually require matching updates in `../../extensions/AGENTS.md`, `../../hooks/AGENTS.md`, and backend slim extension-contract docs.
