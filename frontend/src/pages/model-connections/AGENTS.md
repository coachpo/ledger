# FRONTEND MODEL CONNECTIONS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/model-connections/` owns the global model endpoint inventory/editor route family. It manages stable connection keys, write-only secrets, runtime defaults, reasoning-effort settings, and persisted backend connection tests for Workflow Package reuse.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Inventory list | `list.tsx` | sorted compact platform cards, delete flow, last-test summary |
| Shared editor route | `editor.tsx` | create/edit, key immutability, API style, reasoning effort, secret rotation, inline connection feedback |
| Query + mutation policy | `../../hooks/use-model-connections.ts` | list/detail invalidation, delete flow, persisted test invalidation |
| Secret field UI | `../../components/forms/secret-input.tsx` | write-only credential input behavior |
| Shared route parsing | `../platform-resource-helpers.ts` | required/optional text and numeric parsing helpers |
| Focused tests | `list.test.tsx`, `editor.test.tsx` | route copy, secret handling, reasoning effort, delete/test flows |

## CONVENTIONS
- `list.tsx` is inventory-only: sort by `name` then `modelId`, render `PlatformResourceCard density="compactPlus"`, and keep feedback in toasts plus compact metadata rows.
- `editor.tsx` is the single create/edit surface. The saved `key` is editable on create and immutable on edit.
- Keep Base URL at the provider `/v1` root and let the API-style selector carry Responses vs Chat Completions semantics.
- Blank edit submissions must preserve the stored API key. Only newly entered values rotate the secret.
- Connection tests run only against saved backend records; unsaved drafts should be blocked locally with inline feedback.
- Reasoning-effort handling supports omit, preset, and custom values. Omit sends no reasoning parameter; literal `"none"` stays a string value.
- `deterministic_smoke` connections are the offline/smoke path; API keys remain optional there.

## ANTI-PATTERNS
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
