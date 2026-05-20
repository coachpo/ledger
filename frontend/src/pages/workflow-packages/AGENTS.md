# FRONTEND WORKFLOW PACKAGES PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/workflow-packages/` contains the package-first route family: package inventory, full-height authoring-only YAML/resource editor, local package agents, output schemas, capability profiles, private MCP configs, validation, import/export flows, and the dedicated launch page at `/workflow-packages/:packageId/run` with the `Launch Workflow Package` route label.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Package inventory | `list.tsx` | active package list query, search, current-readiness summaries, import/create/delete entry points |
| Package editor shell | `editor.tsx` | authoring-only overview, agents, output schemas, capability profiles, private MCP, package secret bindings, validation, and export/import tabs |
| Package launch page | `launch.tsx` | dedicated `/workflow-packages/:packageId/run` console for preflight, runtime parameters, saved inputs, and run creation |
| Placeholder shell | `placeholder.tsx` | obsolete placeholder retained only if tests/imports still reference it |
| Editor shell tests | `editor-shell.test.tsx` | full-height authoring shell, tab routing, save/validation behavior, and launch handoff guardrails |
| Resource editor tests | `resource-editors.test.tsx` | local package resource editing and no retired global API imports |
| Launch page tests | `launch.test.tsx` | dedicated launch page metadata, preflight gating, runtime JSON, saved inputs, and run navigation coverage |
| Package list tests | `list.test.tsx` | search, hard-delete, and current-package summary behavior |

## CONVENTIONS
- `editor.tsx` is the authoring hotspot; keep request policy in hooks and local draft/resource editing in the page.
- Package-private resources stay tabbed inside the package editor and never call retired global authoring APIs.
- Capability profile tool pickers use extension-filtered `/api/tools` data from hooks; do not display disabled-extension tools.
- Backend validation diagnostics should deep-link to package-local editor fields when possible.
- Launch belongs to `launch.tsx`, not the editor. Phase 1 keeps `/workflow-packages/:packageId/run` as the live browser route and uses `Launch Workflow Package` as the route label; a `/launch` browser rename is deferred follow-up only.
- The launch page owns preflight gating, workflow selection, runtime parameter JSON, saved-input helpers, and create-run navigation.
- Exports must be previewed and imported through YAML paths that keep private MCP `env`, `headers`, and `query` values inline and still omit database ids.

## ANTI-PATTERNS
- Do not add standalone `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` pages.
- Do not fetch platform data directly from this route; use `use-workflow-packages.ts` and related hooks.
- Do not fork manifest parsing, schema/value codecs, or workflow validation out of `src/lib/platform-authoring/**`.
- Do not put launch/preflight runtime state, run-input registry state, or generated launch controls back into `editor.tsx`.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/workflow-packages/editor-shell.test.tsx src/pages/workflow-packages/resource-editors.test.tsx src/pages/workflow-packages/launch.test.tsx src/pages/workflow-packages/list.test.tsx
```

## NOTES
- `editor.tsx` is intentionally scoped to authoring, validation, package secret bindings, and import/export. It hands launch to the saved-package page instead of running it inside the editor.
- `launch.tsx` owns the dedicated `/workflow-packages/:packageId/run` launch console for phase 1.
- `list.tsx` shows current packages only; delete actions permanently remove packages and rely on query invalidation for list refresh.
- `placeholder.tsx` is not routed by `src/routes.ts`; treat it as leftover placeholder code unless a test explicitly imports it.
