# FRONTEND MODEL CONNECTIONS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW

`src/pages/model-connections/` owns the global model endpoint inventory/editor route family. It manages stable connection keys, write-only secrets, runtime defaults, reasoning-effort settings, and persisted backend connection tests for Workflow Package reuse.

Trusted single-user scope: Inherit the root trusted single-user invariant. Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.

## Compatibility, Upgrades, and Removal Policy

- This repository has no external users yet. Prefer clean architecture, current best practices, and simple maintainable designs over backward-compatibility shims, speculative legacy paths, deprecated API shapes, or compatibility layers.
- During upgrade work, favor the best current implementation and clean internal boundaries. Preserve legacy shapes, migration bridges, fallback behavior, or compatibility shims only when the task explicitly requests them.
- For ordinary removal-only validation, prefer manual confirmation and focused review over adding dedicated “proves not” tests. Keep absence assertions only when the removed or missing surface is itself a shipped contract, safety guardrail, regression boundary, or externally visible behavior.

## WHERE TO LOOK

| Task                    | Location                                  | Notes                                                                                                   |
| ----------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Inventory list          | `list.tsx`                                | sorted inventory surface, delete flow, last-test summary                                                |
| Shared editor route     | `editor.tsx`                              | create/edit, key immutability, API style, reasoning effort, secret rotation, inline connection feedback |
| Query + mutation policy | `../../hooks/use-model-connections.ts`    | list/detail invalidation, delete flow, persisted test invalidation                                      |
| Secret field UI         | `../../components/forms/secret-input.tsx` | write-only credential input behavior                                                                    |
| Shared route parsing    | `../platform-resource-helpers.ts`         | required/optional text and numeric parsing helpers                                                      |
| Focused tests           | `list.test.tsx`, `editor.test.tsx`        | route copy, secret handling, reasoning effort, delete/test flows                                        |

## CONVENTIONS

- `frontend/DESIGN.md` is the source of truth for this route family's page layout, shared shells, tokens, and management UI patterns.
- Because `/model-connections` is metadata `inventory`, `list.tsx` must use the `DESIGN.md` inventory-page pattern: `InventoryPageShell`, `PageContextBar`, `ResourceToolbar`, optional `ResourceFilterBar`, shared state panels, `ResourceTableFrame` or approved shared list/card primitives, selection/bulk/action/delete helpers, and `ResourceStatusBadge`/`ResourceStatusStrip` for statuses.
- Inventory chrome must not be replaced with `WorkspacePageShell`, route-local page wrappers, custom toolbar/filter cards, dashed empty states, or one-off `rounded-md border bg-muted/*` / `shadow-sm` page chrome.
- `list.tsx` is inventory-only: sort by `name` then `modelId`, and keep feedback in toasts plus compact metadata rows.
- `editor.tsx` is the single create/edit surface. The saved `key` is editable on create and immutable on edit.
- Keep Base URL at the provider `/v1` root and let the API-style selector carry Responses vs Chat Completions semantics.
- Blank edit submissions must preserve the stored API key. Only newly entered values rotate the secret.
- Connection tests run only against saved backend records; unsaved drafts should be blocked locally with inline feedback.
- Reasoning-effort handling supports omit, preset, and custom values. Omit sends no reasoning parameter; literal `"none"` stays a string value.
- `deterministic_smoke` connections are the offline/smoke path; API keys remain optional there.
- Route metadata owns the split between the scroll inventory and full-height create/edit editor routes. Keep `route-model-connections-list`, `route-model-connection-new`, and `route-model-connection-edit` aligned with their metadata state variants.
- The create/edit metadata `editor` routes are full-height editors and must use the `DESIGN.md` `WorkspacePageShell` guidance, not inventory shell chrome.
- Inventory navigation, edit, delete, and connection-test actions must remain explicit links or buttons. Never expose saved secrets while testing semantics or error states.

## ANTI-PATTERNS

- Do not add login/logout/account switcher, tenant selector, auth route guards, RBAC UI, or account-management UI unless the product scope changes.
- Do not render saved secrets, blocked secret payloads, or hidden backend error details back into the UI.
- Do not hand-roll cache invalidation in the page; keep it in `use-model-connections.ts`.
- Do not move provider request logic into these routes; keep endpoint calls in `src/lib/api/model-connections.ts`.
- Do not add standalone “proves not” tests for ordinary copy or layout removals here; manual confirmation is enough. Keep absence assertions when they protect secret redaction or another shipped contract.

## VALIDATION

```bash
cd frontend
pnpm test:run src/pages/model-connections/list.test.tsx src/pages/model-connections/editor.test.tsx
pnpm lint
pnpm typecheck
```
