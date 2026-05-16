# FRONTEND EXTENSIONS PAGE GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`. This file covers the live `/extensions` route.

## OVERVIEW
`src/pages/extensions/` owns the system page for inspecting bundled extension state and toggling enabled/disabled status through the backend `/api/extensions` API. It is a state-management surface, not a package-authoring or plugin marketplace surface.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Extensions page | `list.tsx` | list cards, enabled/disabled status, key/label display, and enable/disable switch |
| Page coverage | `list.test.tsx` | renders slim extension state and toggle flows |
| Hooks | `../../hooks/use-extensions.ts` | list/toggle cache policy and finance cache invalidation |
| Runtime consumers | `../../extensions/runtime.tsx` | route/nav/tool visibility reacts to extension state |

## CONVENTIONS
- Use `useExtensions()` and `useToggleExtension()`; do not call API helpers directly from the page.
- Keep `/extensions` under the System nav group assembled in `src/extensions/runtime.tsx`.
- Render only the backend state contract: extension `key`, `label`, and `enabled`. The page only toggles enabled state.

## ANTI-PATTERNS
- Do not treat `/extensions` as package authoring or external plugin installation.
- Do not duplicate extension visibility decisions here; route/nav/tool filtering lives in `src/extensions/runtime.tsx` and hooks.
- Do not reintroduce plugin-manifest fields, reason text, version/state counters, categories, or scaffold details into this page.
