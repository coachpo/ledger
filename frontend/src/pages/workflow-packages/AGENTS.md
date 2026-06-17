# FRONTEND WORKFLOW PACKAGES PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/workflow-packages/` owns the package-first route family: package inventory, a full-height authoring-only YAML/resource editor, a dedicated import workspace for pasted manifest YAML, and the saved-package launch console at `/workflow-packages/:packageId/run`. This folder is where package-local agents, output schemas, capability profiles, private MCP configs, validation, secret bindings, import/export, preflight, saved inputs, and run creation meet the route layer.

Extension model: statically resident extension state filtering.

The repo has no users yet, so prefer clean architecture and current best practices over backward-compatibility shims or speculative legacy paths.

Platform invariant: SignalDeck is a universal agents workflow/pipeline platform. Executable agent workflows must enter and run as Workflow Packages only; standalone global agents, workflows, capabilities, MCP servers, output schemas, skills, Studio, Tryout, orchestration, or runtime-v2 surfaces are removed or outside current goals, not live acceptance paths.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task                              | Location                                                                                                          | Notes                                                                                                                           |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Package inventory                 | `list.tsx`                                                                                                        | active package list query, search, readiness summaries, import/create/delete entry points                                       |
| Package editor shell              | `editor.tsx`                                                                                                      | authoring-only overview, agents, output schemas, capability profiles, private MCP, secret bindings, validation, and export tabs |
| Editor section helpers            | `editor-sections.tsx`                                                                                             | large tab/section helper surface for package-local resources, validation detail rendering, and repeated editor chrome            |
| Import workspace                  | `import-page.tsx`                                                                                                 | pasted YAML import, before-unload and route-leave confirmation, and backend validation-detail rendering                         |
| Package launch page               | `launch.tsx`                                                                                                      | dedicated `/workflow-packages/:packageId/run` console for preflight, runtime parameters, saved inputs, and run creation         |
| Editor and resource coverage      | `editor-shell.test.tsx`, `resource-editors.test.tsx`, `secret-bindings.test.tsx`, `http-node-validation.test.tsx` | full-height editor shell, resource editing, secret bindings, and private MCP HTTP/SSE validation                                |
| Import / launch / export coverage | `import-page.test.tsx`, `launch.test.tsx`, `preflight-launch-export.test.tsx`, `list.test.tsx`                    | import workspace behavior, launch console, preflight/export flows, and inventory behavior                                       |

## CONVENTIONS

- `frontend/DESIGN.md` is the source of truth for this route family's page layout, shared shells, tokens, and management UI patterns.
- Because `/workflow-packages` is metadata `inventory`, `list.tsx` must use the `DESIGN.md` inventory-page pattern: `InventoryPageShell`, `PageContextBar`, `ResourceToolbar`, optional `ResourceFilterBar`, shared state panels, `ResourceTableFrame` or approved shared list/card primitives, selection/bulk/action/delete helpers, and `ResourceStatusBadge`/`ResourceStatusStrip` for statuses.
- Import/new/detail metadata `editor` routes and the launch metadata `console` route are full-height routes and must use the `DESIGN.md` `WorkspacePageShell` guidance, not inventory shell chrome.
- Inventory chrome must not be replaced with `WorkspacePageShell`, route-local page wrappers, custom toolbar/filter cards, dashed empty states, or one-off `rounded-md border bg-muted/*` / `shadow-sm` page chrome.
- `editor.tsx` is the authoring hotspot; keep request policy in hooks and local draft/resource editing in the page.
- Package-private resources stay tabbed inside the editor and never call retired global authoring APIs.
- Capability profile tool pickers use extension-filtered `useTools()` data from hooks; disabled-extension tools must not appear as selectable package capability keys.
- Backend validation diagnostics should deep-link to package-local editor fields when possible.
- Import belongs to `import-page.tsx`, not the editor. The import workspace owns pasted manifest YAML, unsaved/active-import navigation blocking, and detailed backend rejection messages.
- Launch belongs to `launch.tsx`, not the editor. Phase 1 keeps `/workflow-packages/:packageId/run` as the live browser route and uses `Launch Workflow Package` as the route label; a `/launch` browser rename is deferred follow-up only.
- The launch page owns preflight gating, workflow selection, runtime parameter JSON, saved-input registry helpers, and create-run navigation.
- Browser-visible manifest reads and exports must omit private MCP `env`, `headers`, and `query` values while still omitting database ids and run history; imports may accept those fields as secret-bearing package-private authoring/runtime config.
- Route metadata owns shell mode for this family: list is `inventory` and scroll, import/new/detail are `editor` and full height, and `/workflow-packages/:packageId/run` is `console` and full height.
- Inventory cards and tables use explicit package open, launch, delete, selection, and bulk-action controls. Do not make the whole row or card a pointer-only target.
- Browser coverage for this family must keep package-first authoring, import/export, dedicated launch, snapshot provenance, and wide run payload overflow checks.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not add standalone `/agents*`, `/capabilities*`, `/mcp-servers*`, `/output-schemas*`, or `/workflows*` pages.
- Do not fetch platform data directly from this route family; use `use-workflow-packages.ts` and related hooks.
- Do not fork manifest parsing, schema/value codecs, or workflow validation out of `src/lib/platform-authoring/**`.
- Do not move import-page leave guards, preflight state, runtime-input registry state, or generated launch controls back into `editor.tsx`.
- Do not collapse backend validation details into generic toasts when the route already has a dedicated error surface.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/workflow-packages/editor-shell.test.tsx src/pages/workflow-packages/resource-editors.test.tsx src/pages/workflow-packages/secret-bindings.test.tsx src/pages/workflow-packages/http-node-validation.test.tsx src/pages/workflow-packages/import-page.test.tsx src/pages/workflow-packages/launch.test.tsx src/pages/workflow-packages/preflight-launch-export.test.tsx src/pages/workflow-packages/list.test.tsx
```

## NOTES

- `editor.tsx` is intentionally scoped to authoring, validation, package secret bindings, and export/import handoff. It hands launch to the saved-package page instead of running it inside the editor.
- `import-page.tsx` is the only live full-height pasted-manifest import surface.
- `launch.tsx` owns the dedicated `/workflow-packages/:packageId/run` launch console for phase 1.
- `list.tsx` shows current packages only; delete actions permanently remove packages and rely on query invalidation for list refresh.
