# FRONTEND WORKFLOW PACKAGES PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/workflow-packages/` contains the package-first authoring route family: package inventory, full-height YAML/resource editor, local package agents, output schemas, capability profiles, private MCP configs, validation, preflight, launch, import, and export flows with inline `env`, `headers`, and `query` values.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are retired/archive context, not live acceptance paths.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Package inventory | `list.tsx` | active package list query, search, version summaries, import/create/delete entry points |
| Package editor shell | `editor.tsx` | overview, agents, output schemas, capability profiles, private MCP, preflight, launch, export/import tabs |
| Placeholder shell | `placeholder.tsx` | obsolete placeholder retained only if tests/imports still reference it |
| Editor shell tests | `editor-shell.test.tsx` | full-height shell, tab routing, save/validation behavior |
| Resource editor tests | `resource-editors.test.tsx` | local package resource editing and no retired global API imports |
| Preflight / launch tests | `preflight-launch-export.test.tsx` | blocking diagnostics, generated launch form labels/help text, import/export contract coverage |
| Package list tests | `list.test.tsx` | search, hard-delete, and version-summary behavior |

## CONVENTIONS
- `editor.tsx` is the route-family hotspot; keep request policy in hooks and local draft/resource editing in the page.
- Package-private resources stay tabbed inside the package editor and never call retired global authoring APIs.
- Capability profile tool pickers use extension-filtered `/api/tools` data from hooks; do not display disabled-extension tools.
- Backend validation diagnostics should deep-link to package-local editor fields when possible.
- Launch forms are generated from workflow input schemas and honor supported `title`/`description` metadata.
- Exports must be previewed and imported through YAML paths that keep private MCP `env`, `headers`, and `query` values inline and still omit database ids.

## ANTI-PATTERNS
- Do not add standalone `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` pages.
- Do not fetch platform data directly from this route; use `use-workflow-packages.ts` and related hooks.
- Do not fork manifest parsing, schema/value codecs, or workflow validation out of `src/lib/platform-authoring/**`.

## VALIDATION
```bash
cd frontend
pnpm test:run src/pages/workflow-packages/editor-shell.test.tsx src/pages/workflow-packages/resource-editors.test.tsx src/pages/workflow-packages/preflight-launch-export.test.tsx src/pages/workflow-packages/list.test.tsx
```

## NOTES
- `editor.tsx` is intentionally large because it composes every package authoring tab and launch/export flow.
- `list.tsx` shows current packages only; delete actions permanently remove packages and rely on query invalidation for list refresh.
- `placeholder.tsx` is not routed by `src/routes.ts`; treat it as leftover placeholder code unless a test explicitly imports it.
