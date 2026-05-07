# FRONTEND MODEL CONNECTIONS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/model-connections/` contains the routed saved-model-endpoint inventory and editor. These pages manage OpenAI-family base URLs, credentials, model ids, reasoning effort, timeout defaults, archive state, and connection-test feedback for agents that reference saved connections.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| Model-connection inventory | `list.tsx` | list query, sorted table, archive action, last-test badges |
| Model-connection editor | `editor.tsx` | create/update form, secret preservation, inline connection test |
| Hooks | `../../hooks/use-model-connections.ts` | list/detail/create/update/archive/test mutations and invalidation |
| API helpers | `../../lib/api/model-connections.ts` | `/api/model-connections` request helpers |
| Wire types | `../../lib/types/model-connection.ts` | create/update/read/status/reasoning-effort contracts |
| Shared platform helpers | `../platform-resource-shared.tsx` | numeric parsing, required text parsing, status badges |

## CONVENTIONS
- Create/edit share `ModelConnectionsEditorPage`; the route param decides whether detail data loads.
- The API key field is write-only in the UI: blank edit submissions preserve the stored key, while non-empty input rotates it.
- Connection testing is only available after the model connection is saved and uses the persisted backend connection-test endpoint.
- List rows show archived connections because existing agents may still reference them, but new agent saves should choose active connections.
- Pages own navigation, toasts, local draft state, and inline feedback; hooks own server-state policy.

## ANTI-PATTERNS
- Do not expose stored API key values or derived key-presence metadata in the editor or list views; credentials are write-only and backend-owned.
- Do not call the model-connection API directly from the page when a hook already exists.
- Do not let archived connections become selectable for new agent bindings.
- Do not duplicate URL, timeout, or secret validation here when backend schemas enforce the contract.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
